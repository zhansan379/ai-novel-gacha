"""内存 Story 存储（MVP）。用 anyio.Lock 保证并发访问安全；SQLite 落地后替换接口。"""
from __future__ import annotations

from dataclasses import dataclass, field

import anyio

from app.schemas import Card, DirectionSpec


class StoryNotFound(KeyError):
    pass


class DecisionLocked(ValueError):
    pass


@dataclass
class Decision:
    """一次剧情分歧：候选卡池 + 最终采用的模式/方向。"""

    no: int
    cards: list[Card] = field(default_factory=list)
    pool_version: int = 1
    mode: str | None = None
    card_id: str | None = None
    direction_spec: DirectionSpec | None = None
    applied: bool = False
    # 本步推进前的角色/伏笔快照（供"撤销上一步"还原），None 表示无可回滚的状态
    rollback: dict | None = None


@dataclass
class Story:
    id: str
    premise: str
    synopsis: str = ""
    passages: list[dict] = field(default_factory=list)  # {no, decision_no, content, lint, consistency}
    decisions: dict[int, Decision] = field(default_factory=dict)
    next_decision_no: int = 1
    # 前置构建蓝图（世界观 / 历史线 / 角色）
    world: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    characters: list = field(default_factory=list)
    style_profile_id: str = "restrained"
    # 伏笔账本：[{id, text, origin, status: planted|advanced|paid_off}]
    foreshadows: list = field(default_factory=list)
    # 剧情时间线（复盘账本）：随每次决策追加，{no, decision_no, mode, card_id, label, title, summary}
    # 与 world.history（世界历史线·固定背景）是两回事，二者互不影响。
    timeline: list = field(default_factory=list)

    def milestone(self) -> Decision:
        """返回当前待决策节点；不存在则创建。"""
        d = self.decisions.get(self.next_decision_no)
        if d is None:
            d = Decision(no=self.next_decision_no)
            self.decisions[d.no] = d
        return d

    def last_decision_applied(self) -> int:
        return max((k for k, v in self.decisions.items() if v.applied), default=0)

    def advance(self) -> Decision:
        self.next_decision_no += 1
        return self.milestone()


class StoryStore:
    def __init__(self) -> None:
        self._data: dict[str, Story] = {}
        self._lock = anyio.Lock()

    def get(self, story_id: str) -> Story:
        story = self._data.get(story_id)
        if story is None:
            raise StoryNotFound(story_id)
        return story

    async def save(self, story: Story) -> None:
        async with self._lock:
            self._data[story.id] = story

    def snapshot(self, story_id: str) -> dict:
        story = self.get(story_id)
        return {
            "story_id": story.id,
            "premise": story.premise,
            "synopsis": story.synopsis,
            "next_decision_no": story.next_decision_no,
            "style_profile_id": story.style_profile_id,
            "passages": [
                {"no": p["no"], "decision_no": p.get("decision_no"), "content": p["content"]}
                for p in story.passages
            ],
            "decisions": [
                {
                    "no": d.no, "pool_version": d.pool_version, "mode": d.mode,
                    "card_id": d.card_id, "applied": d.applied,
                    "cards": [c.model_dump(mode="json") for c in d.cards],
                    "direction_spec": d.direction_spec.model_dump(mode="json") if d.direction_spec else None,
                    "rollback": d.rollback,
                }
                for d in story.decisions.values()
            ],
            "world": story.world, "history": story.history, "characters": story.characters,
            "foreshadows": story.foreshadows, "timeline": story.timeline,
        }

    def delete(self, story_id: str) -> bool:
        return self._data.pop(story_id, None) is not None

    def import_snapshot(self, data: dict) -> Story:
        import uuid

        story = Story(
            id=str(uuid.uuid4()),
            premise=data.get("premise", ""),
            synopsis=data.get("synopsis", "") or "",
            passages=[
                {"no": p.get("no"), "decision_no": p.get("decision_no"),
                 "content": p.get("content") or ""}
                for p in (data.get("passages") or [])
            ],
            next_decision_no=int(data.get("next_decision_no") or 1),
            world=data.get("world") or {},
            history=data.get("history") or [],
            characters=data.get("characters") or [],
            style_profile_id=data.get("style_profile_id") or "restrained",
            foreshadows=data.get("foreshadows") or [],
            timeline=data.get("timeline") or [],
        )
        from app.schemas import Card, DirectionSpec

        for obj in (data.get("decisions") or []):
            d = Decision(
                no=int(obj["no"]),
                pool_version=int(obj.get("pool_version", 1)),
                mode=obj.get("mode"),
                card_id=obj.get("card_id"),
                applied=bool(obj.get("applied", False)),
                cards=[Card.model_validate(c) for c in (obj.get("cards") or [])],
                direction_spec=DirectionSpec.model_validate(obj["direction_spec"])
                if obj.get("direction_spec") else None,
                rollback=obj.get("rollback"),
            )
            story.decisions[d.no] = d
        self._data[story.id] = story
        return story

    def list(self) -> list[dict]:
        """返回全部故事的精简概览（书架用），按创建先后倒序。"""
        return [
            {
                "story_id": s.id,
                "premise": s.premise,
                "synopsis": s.synopsis,
                "next_decision_no": s.next_decision_no,
            }
            for s in reversed(list(self._data.values()))
        ]

    def reset(self) -> None:
        self._data.clear()