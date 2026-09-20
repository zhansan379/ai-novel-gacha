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


@dataclass
class Story:
    id: str
    premise: str
    synopsis: str = ""
    passages: list[dict] = field(default_factory=list)  # {no, decision_no, content, lint, consistency}
    decisions: dict[int, Decision] = field(default_factory=dict)
    next_decision_no: int = 1
    # 前置构建蓝图（世界观 / 历史线 / 角色 / 卷·章大纲）
    world: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    characters: list = field(default_factory=list)
    outline: list = field(default_factory=list)
    style_profile_id: str = "restrained"

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

    def reset(self) -> None:
        self._data.clear()