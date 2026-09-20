"""故事服务：开书初始化 + 决策应用（生成方向对应的下一段正文）。"""
from __future__ import annotations

import uuid

from app.consistency.checker import ConsistencyChecker
from app.deslop import scan as deslop_scan
from app.llm import LLMGateway
from app.schemas import DirectionKind, DirectionSpec
from app.services.direction import DirectionGenerator
from app.services.store import Story, StoryStore
from app.services.writer import WriterAgent

_INIT_SYSTEM = """你是小说开书编辑。根据一句话灵感，产出一段简洁的世界观与大纲简介（150 字内），
说明核心设定、主角目标与可能的冲突走向。只输出简介本身。"""


class StoryService:
    def __init__(self, store: StoryStore, gateway: LLMGateway,
                 direction: DirectionGenerator, writer: WriterAgent) -> None:
        self._store = store
        self._gateway = gateway
        self._direction = direction
        self._writer = writer
        self._consistency = ConsistencyChecker(gateway)

    async def _quality(self, premise: str, synopsis: str, content: str) -> tuple[dict, dict]:
        """生成后的质检：去 AI 味 lint + 一致性校验。"""
        lint = deslop_scan(content)
        consistency = await self._consistency.check(
            premise=premise, synopsis=synopsis, passage=content,
        )
        return lint, consistency

    async def review(self, *, premise: str, synopsis: str, content: str) -> dict:
        """公开质检入口（供重扫端点使用）。"""
        lint, consistency = await self._quality(premise, synopsis, content)
        return {"lint": lint, "consistency": consistency}

    async def create(self, premise: str) -> Story:
        synopsis = await self._gateway.complete(task="init", system=_INIT_SYSTEM, user=premise)
        story = Story(id=str(uuid.uuid4()), premise=premise, synopsis=synopsis.strip())
        decision = story.milestone()
        decision.cards = await self._direction.generate(
            premise=premise, synopsis=synopsis, tail="", decision_no=decision.no,
        )
        opening = await self._writer.generate(premise=premise, synopsis=synopsis, direction=None)
        lint, consistency = await self._quality(premise, synopsis, opening)
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

        tail = story.passages[-1]["content"] if story.passages else ""
        prose = await self._writer.generate(
            premise=story.premise, synopsis=story.synopsis, direction=direction_spec, tail=tail,
        )
        lint, consistency = await self._quality(story.premise, story.synopsis, prose)
        passage = {"no": len(story.passages) + 1, "decision_no": decision_no,
                   "content": prose.strip(), "lint": lint, "consistency": consistency}
        story.passages.append(passage)

        # 预生成下一分歧点的卡池
        next_d = story.advance()
        next_d.cards = await self._direction.generate(
            premise=story.premise, synopsis=story.synopsis, tail=prose, decision_no=next_d.no,
        )
        self._store.save(story)
        return passage

    @staticmethod
    def spec_from_instruction(text: str) -> DirectionSpec:
        return DirectionSpec(kind=DirectionKind.CUSTOM, summary=text.strip()[:200], risk_flag=True)