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
from app.services.narrative import NarrativeUpdater
from app.services.store import Story, StoryStore
from app.services.styles import get_style
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


class StoryService:
    def __init__(self, store: StoryStore, gateway: LLMGateway,
                 direction: DirectionGenerator, writer: WriterAgent) -> None:
        self._store = store
        self._gateway = gateway
        self._direction = direction
        self._writer = writer
        self._blueprint = BlueprintBuilder(gateway)
        self._consistency = ConsistencyChecker(gateway)
        self._narrative = NarrativeUpdater(gateway)

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

    async def create(self, premise: str, style_profile_id: str | None = None) -> Story:
        synopsis = await self._gateway.complete(task="init", system=_INIT_SYSTEM, user=premise)
        story = Story(id=str(uuid.uuid4()), premise=premise, synopsis=synopsis.strip(),
                      style_profile_id=get_style(style_profile_id).id)

        # 前置构建：世界观 / 历史线 / 角色 / 伏笔种子（不再产出预设卷章大纲）
        bp = await self._blueprint.build(premise=premise, synopsis=synopsis)
        story.world = bp.get("world") or {}
        story.history = bp.get("history") or []
        story.characters = bp.get("characters") or []
        story.foreshadows = init_foreshadows(bp.get("foreshadow_seeds") or [])

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

        # 还原角色/伏笔到本步推进前
        if decision.rollback:
            story.characters = decision.rollback.get("characters") or story.characters
            story.foreshadows = decision.rollback.get("foreshadows") or story.foreshadows

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

    async def _advance_state(self, story: Story, direction_spec: DirectionSpec | None,
                             passage: str) -> None:
        """决策后：若命中变点，让伏笔/角色随这拍剧情推进，成为后续生成/质检的上下文。"""
        if direction_spec is None:
            return
        if not self._narrative.should_run(
                kind=direction_spec.kind, passage=passage,
                characters=story.characters, foreshadows=story.foreshadows):
            return
        try:
            chars, fs = await self._narrative.update(
                premise=story.premise, synopsis=story.synopsis,
                characters=story.characters, foreshadows=story.foreshadows, passage=passage,
            )
            story.characters = chars
            story.foreshadows = fs
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
        await self._advance_state(story, direction_spec, prose.strip())

        # 预生成下一分歧点的卡池（基于推进后的状态）
        next_d = story.advance()
        next_d.cards = await self._direction.generate(
            premise=story.premise, synopsis=story.synopsis, tail=prose, decision_no=next_d.no,
            context=build_narrative_context(story),
        )
        self._store.save(story)
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
        except Exception:
            decision.applied = False  # 出错回滚，允许重试
            raise

        content = "".join(pieces).strip()
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
            context=build_narrative_context(story),
        )
        self._store.save(story)
        yield {"type": "end", "passage": passage, "next_decision_no": story.next_decision_no}

    @staticmethod
    def spec_from_instruction(text: str) -> DirectionSpec:
        return DirectionSpec(kind=DirectionKind.CUSTOM, summary=text.strip()[:200], risk_flag=True)