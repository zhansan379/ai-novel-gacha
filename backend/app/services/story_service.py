"""故事服务：开书初始化 + 决策应用（生成方向对应的下一段正文）。"""
from __future__ import annotations

import copy
import uuid

from app.consistency.checker import ConsistencyChecker
from app.deslop import scan as deslop_scan
from app.llm import LLMGateway
from app.schemas import DirectionKind, DirectionSpec
from app.services.blueprint import BlueprintBuilder
from app.services.direction import DirectionGenerator
from app.services.facts import build_facts, build_narrative_context, init_foreshadows
from app.services.grounding import GroundingService
from app.services.narrative import NarrativeUpdater
from app.services.store import Story, StoryStore
from app.services.styles import DEFAULT_STYLE_ID, get_style, match_style_id, style_choice_text
from app.services.writer import WriterAgent

_INIT_SYSTEM = """你是小说开书编辑。根据一句话灵感，产出一段简洁的世界观与大纲简介（150 字内），
说明核心设定、主角目标与可能的冲突走向。只输出简介本身。"""


def _beat_summary(text: str, limit: int = 60) -> str:
    """从正文中截取第一句作为这一剧情拍的摘要（本地提取，不额外调 LLM）。"""
    t = (text or "").strip()
    for i, ch in enumerate(t):
        if ch in "。！？.!?":
            t = t[: i + 1]
            break
    return t[:limit] or t


def _pending_hook(spec: DirectionSpec | None) -> str:
    """从已落定的方向里取出下一拍应回收的悬念/后果，作为下一轮卡池的延续输入。"""
    if spec is None:
        return ""
    parts = []
    if getattr(spec, "suspense", None):
        parts.append(f"上一拍留下的悬念：{spec.suspense}")
    if getattr(spec, "aftermath", None):
        parts.append(f"上一事件的去向：{spec.aftermath}")
    return "\n".join(parts)


class StoryService:
    def __init__(self, store: StoryStore, gateway: LLMGateway,
                 direction: DirectionGenerator, writer: WriterAgent,
                 grounding: GroundingService | None = None) -> None:
        self._store = store
        self._gateway = gateway
        self._direction = direction
        self._writer = writer
        self._blueprint = BlueprintBuilder(gateway)
        self._consistency = ConsistencyChecker(gateway)
        self._narrative = NarrativeUpdater(gateway)
        self._grounding = grounding or GroundingService()

    def _append_timeline(self, story: Story, decision, no: int, content: str) -> None:
        """把刚生成的这一剧情拍追加进时间线（复盘账本），不触碰世界历史线 world.history。"""
        card = None
        if decision.card_id:
            card = next((c for c in decision.cards if c.card_id == decision.card_id), None)
        story.timeline.append({
            "no": no,
            "decision_no": decision.no,
            "mode": decision.mode,
            "card_id": decision.card_id,
            "label": card.label.value if card else decision.mode,
            "title": card.title if card else None,
            "summary": _beat_summary(content),
        })

    async def _quality(self, premise: str, synopsis: str, content: str,
                       facts: list[str] | None = None) -> tuple[dict, dict]:
        """生成后的质检：去 AI 味 lint + 基于设定事实的一致性命。"""
        lint = deslop_scan(content)
        consistency = await self._consistency.check(
            premise=premise, synopsis=synopsis, passage=content, facts=facts,
        )
        return lint, consistency

    async def review(self, *, premise: str, synopsis: str, content: str,
                     facts: list[str] | None = None) -> dict:
        """公开质检入口（供重扫端点使用）。"""
        lint, consistency = await self._quality(premise, synopsis, content, facts=facts)
        return {"lint": lint, "consistency": consistency}

    async def _auto_style(self, premise: str, synopsis: str) -> str:
        """根据前提与简介，让模型挑一套最贴切的文风；失败时回退默认文风。"""
        system = (
            "你是小说文风选择器。根据小说前提与简介，从给定文风里挑出最贴合的一种，"
            "用于决定整本书的文字腔调。只输出一个文风 id（英文字母，不要标点、不要解释）。"
        )
        user = (
            f"可选文风：\n{style_choice_text()}\n\n"
            f"【小说前提】{premise}\n【小说简介】{synopsis}\n\n最贴合的文风 id："
        )
        try:
            raw = await self._gateway.complete(task="init", system=system, user=user)
            return match_style_id(raw) or DEFAULT_STYLE_ID
        except Exception:
            return DEFAULT_STYLE_ID

    async def create(self, premise: str, style_profile_id: str | None = None) -> Story:
        synopsis = await self._gateway.complete(task="init", system=_INIT_SYSTEM, user=premise)
        chosen = (style_profile_id or "").strip()
        if not chosen or chosen == "auto":
            chosen = await self._auto_style(premise, synopsis)
        story = Story(id=str(uuid.uuid4()), premise=premise, synopsis=synopsis.strip(),
                      style_profile_id=get_style(chosen).id)

        # 真实世界事实基座：检索内置知识库（可选联网），把命中真实人物/产品的事实注入蓝图
        grounding_res = await self._grounding.resolve(premise, synopsis=synopsis)
        story.grounding = grounding_res.facts

        # 前置构建：世界观 / 历史线 / 角色 / 伏笔种子（不再产出预设卷章大纲）
        bp = await self._blueprint.build(
            premise=premise, synopsis=synopsis,
            grounding=self._grounding.facts_text(grounding_res),
        )
        story.world = bp.get("world") or {}
        story.history = bp.get("history") or []
        story.characters = bp.get("characters") or []
        story.foreshadows = init_foreshadows(bp.get("foreshadow_seeds") or [])
        story.relations = bp.get("relationships") or []

        decision = story.milestone()
        decision.cards = await self._direction.generate(
            premise=premise, synopsis=synopsis, tail="", decision_no=decision.no,
            context=build_narrative_context(story),
        )
        opening = await self._writer.generate(premise=premise, synopsis=synopsis, direction=None,
                                              style_profile_id=story.style_profile_id,
                                              context=build_narrative_context(story))
        lint, consistency = await self._quality(premise, synopsis, opening, facts=build_facts(story))
        story.passages.append({"no": 1, "decision_no": None, "content": opening.strip(),
                               "lint": lint, "consistency": consistency})
        self._store.save(story)
        return story

    def get(self, story_id: str) -> Story:
        return self._store.get(story_id)

    def list(self) -> list[dict]:
        """返回全部故事的精简概览（书架用）。"""
        return self._store.list()

    def export_snapshot(self, story_id: str) -> dict:
        return self._store.snapshot(story_id)

    def import_snapshot(self, data: dict) -> Story:
        return self._store.import_snapshot(data)

    def delete(self, story_id: str) -> bool:
        return self._store.delete(story_id)

    def _current_decision(self, story: Story, decision_no: int):
        decision = story.decisions.get(decision_no)
        if decision is None:
            raise KeyError(f"决策节点不存在: {decision_no}")
        return decision

    async def undo_last(self, story: Story) -> dict:
        """撤销上一步：回退最后一条正文/时间线，解锁该决策并还原角色与伏笔快照。"""
        last_no = story.next_decision_no - 1
        decision = story.decisions.get(last_no)
        if last_no < 1 or decision is None or not decision.applied:
            raise ValueError("没有可撤销的上一步")

        # 还原角色/伏笔/关系到本步推进前（relations 用键存在性判断，空列表也是合法回滚值）
        if decision.rollback:
            story.characters = decision.rollback.get("characters") or story.characters
            story.foreshadows = decision.rollback.get("foreshadows") or story.foreshadows
            if "relations" in decision.rollback:
                story.relations = decision.rollback["relations"]

        # 移除本步生成的正文与时间线条目
        story.passages = [p for p in story.passages if p.get("decision_no") != last_no]
        story.timeline = [t for t in story.timeline if t.get("decision_no") != last_no]

        # 解锁该决策（保留卡池，可重新选择）
        decision.applied = False
        decision.mode = None
        decision.card_id = None
        decision.direction_spec = None
        decision.rollback = None
        story.next_decision_no = last_no

        self._store.save(story)
        return {"undo": True, "next_decision_no": last_no,
                "passages_remaining": len(story.passages)}

    @staticmethod
    def _rollback_decision(story: Story, decision, decision_no: int) -> None:
        """决策中途失败时回滚：解锁、移除未持久化的段落/时间线、还原角色/伏笔/关系快照。"""
        decision.applied = False
        decision.mode = None
        decision.card_id = None
        decision.direction_spec = None
        story.passages = [p for p in story.passages if p.get("decision_no") != decision_no]
        story.timeline = [t for t in story.timeline if t.get("decision_no") != decision_no]
        if decision.rollback:
            story.characters = decision.rollback.get("characters") or story.characters
            story.foreshadows = decision.rollback.get("foreshadows") or story.foreshadows
            # 空关系列表是合法回滚值，用键存在性而非真值判断
            if "relations" in decision.rollback:
                story.relations = decision.rollback["relations"]
        story.next_decision_no = decision_no  # 回到本决策，可重试

    async def _advance_state(self, story: Story, direction_spec: DirectionSpec | None,
                             passage: str) -> None:
        """决策后：按剧情浓度推进伏笔/角色/关系，成为后续生成/质检的上下文。"""
        if direction_spec is None:
            return
        plan = self._narrative.advance_plan(
            kind=direction_spec.kind, passage=passage,
            characters=story.characters, foreshadows=story.foreshadows,
        )
        if not plan.any:
            return
        try:
            chars, fs, rels = await self._narrative.update(
                premise=story.premise, synopsis=story.synopsis,
                characters=story.characters, foreshadows=story.foreshadows,
                relations=story.relations, passage=passage,
                advance_characters=plan.advance_characters,
                advance_foreshadows=plan.advance_foreshadows,
                advance_relations=plan.advance_relations,
            )
            story.characters = chars
            story.foreshadows = fs
            story.relations = rels
        except Exception:
            pass  # 状态更新为辅助步骤，失败不阻断正文流程

    async def apply_decision(self, story: Story, decision_no: int, mode: str,
                             direction_spec: DirectionSpec, card_id: str | None = None) -> dict:
        """锁定决策 → 生成对应正文（含质检） → 推进下一决策 → 返回该段正文。"""
        decision = self._current_decision(story, decision_no)
        if decision.applied:
            from app.services.store import DecisionLocked
            raise DecisionLocked(decision_no)

        decision.mode = mode
        decision.card_id = card_id
        decision.direction_spec = direction_spec
        decision.applied = True
        decision.rollback = {
            "characters": copy.deepcopy(story.characters),
            "foreshadows": copy.deepcopy(story.foreshadows),
            "relations": copy.deepcopy(story.relations),
        }

        tail = story.passages[-1]["content"] if story.passages else ""
        prose = await self._writer.generate(
            premise=story.premise, synopsis=story.synopsis, direction=direction_spec, tail=tail,
            style_profile_id=story.style_profile_id, context=build_narrative_context(story),
        )
        lint, consistency = await self._quality(story.premise, story.synopsis, prose,
                                            facts=build_facts(story))
        passage = {"no": len(story.passages) + 1, "decision_no": decision_no,
                   "content": prose.strip(), "lint": lint, "consistency": consistency}
        story.passages.append(passage)
        self._append_timeline(story, decision, passage["no"], prose.strip())
        try:
            await self._advance_state(story, direction_spec, prose.strip())
            # 预生成下一分歧点的卡池（基于推进后的状态）
            next_d = story.advance()
            next_d.cards = await self._direction.generate(
                premise=story.premise, synopsis=story.synopsis, tail=prose, decision_no=next_d.no,
                context=build_narrative_context(story), carryover=_pending_hook(direction_spec),
            )
            self._store.save(story)
        except Exception:
            self._rollback_decision(story, decision, decision_no)
            raise
        return passage

    async def apply_decision_stream(self, story: Story, decision_no: int, mode: str,
                                    direction_spec: DirectionSpec, card_id: str | None = None):
        """流式版 apply：锁定 → 逐块生成正文 → 质检/存储/推进 → yield 事件 dict。

        事件 dict 形态：{"type": "start"|"delta"|"end", ...}，由路由层转发为 SSE 事件。
        若中途出错，回滚 decision.applied 以便重试。
        """
        decision = self._current_decision(story, decision_no)
        if decision.applied:
            from app.services.store import DecisionLocked
            raise DecisionLocked(decision_no)

        decision.mode = mode
        decision.card_id = card_id
        decision.direction_spec = direction_spec
        decision.applied = True
        decision.rollback = {
            "characters": copy.deepcopy(story.characters),
            "foreshadows": copy.deepcopy(story.foreshadows),
            "relations": copy.deepcopy(story.relations),
        }

        tail = story.passages[-1]["content"] if story.passages else ""
        yield {"type": "start", "decision_no": decision_no, "mode": mode, "card_id": card_id}

        pieces: list[str] = []
        try:
            async for chunk in self._writer.stream_generate(
                premise=story.premise, synopsis=story.synopsis, direction=direction_spec,
                tail=tail, style_profile_id=story.style_profile_id,
                context=build_narrative_context(story),
            ):
                pieces.append(chunk)
                yield {"type": "delta", "text": chunk}
        except Exception as exc:
            # 正文流中途失败：回滚该决策，发干净的错误事件（避免已开始的流上再抛异常）
            self._rollback_decision(story, decision, decision_no)
            yield {"type": "error", "message": str(exc)}
            return

        content = "".join(pieces).strip()
        try:
            lint, consistency = await self._quality(story.premise, story.synopsis, content,
                                                    facts=build_facts(story))
            passage = {"no": len(story.passages) + 1, "decision_no": decision_no,
                       "content": content, "lint": lint, "consistency": consistency}
            story.passages.append(passage)
            self._append_timeline(story, decision, passage["no"], content)
            await self._advance_state(story, direction_spec, content)

            next_d = story.advance()
            next_d.cards = await self._direction.generate(
                premise=story.premise, synopsis=story.synopsis, tail=content, decision_no=next_d.no,
                context=build_narrative_context(story), carryover=_pending_hook(direction_spec),
            )
            self._store.save(story)
        except Exception as exc:
            # 正文已流式发出但收尾失败：回滚该决策，并抛出一个干净的 SSE 错误事件，
            # 避免在已开始的流上抛异常导致 "Response already started"。
            self._rollback_decision(story, decision, decision_no)
            yield {"type": "error", "message": str(exc)}
            return
        yield {"type": "end", "passage": passage, "next_decision_no": story.next_decision_no}

    @staticmethod
    def spec_from_instruction(text: str) -> DirectionSpec:
        return DirectionSpec(kind=DirectionKind.CUSTOM, summary=text.strip()[:200], risk_flag=True)