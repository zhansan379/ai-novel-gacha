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
class Chapter:
    """一章：覆盖一段连续的正文段（passage_from..passage_to，含端点）。

    章节边界由 LLM 在续写时按剧情拍感判定（见 progression.judge）：“open”表示本章仍在
    收集正文段，被 LLM 判定收束后置为“closed”并开下一章。最后一章 finished 置 True
    表示全书结局章（story.status == "completed"）。
    """

    no: int
    title: str = ""
    passage_from: int = 0
    passage_to: int = 0
    is_final: bool = False
    summary: str = ""
    status: str = "open"  # "open" | "closed"


@dataclass
class Story:
    id: str
    premise: str
    # 归属用户：公网多用户隔离用，空串表示传统无主/本地数据
    user_id: str = ""
    synopsis: str = ""
    # 简介出厂事实校验门结果：{checked, passed, issues, retries, ...}；空 dict = 老故事/未做校验。
    synopsis_checked: dict = field(default_factory=dict)
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
    # 真实世界事实基座（内置知识库/联网检索）：随每次决策注入生成 prompt，约束尊重史实
    grounding: list = field(default_factory=list)
    # 检索画像（本书记录的一次判定 + 预取来源）：{real_world, profession, timeliness, continuity,
    # topics, require_web, genre}，驱动本稿的网络搜索与正文增量联网决策。空 dict=老故事/未判定，走纯召回。
    retrieval_profile: dict = field(default_factory=dict)
    # 主题材（profiling 判定，顶层字段供前端直接展示；老故事为空串，读 retrieval_profile.genre 兜底）。
    genre: str = ""
    # 关系账本（知识图谱边）：[{a, b, label, note}]，无向边 a/b 顺序无关。
    # 初始化来自蓝图，随后随每次决策经 narrative.update 的 relation_updates 增量演进；
    # 注入 build_facts/build_narrative_context，供质检与生成遵守跨实体事实。
    relations: list = field(default_factory=list)
    # 剧情时间线（复盘账本）：随每次决策追加，{no, decision_no, mode, card_id, label, title, summary}
    # 与 world.history（世界历史线·固定背景）是两回事，二者互不影响。
    timeline: list = field(default_factory=list)
    # 章节目录：连续正文段落的分组，见 Chapter。故事完结时 status == "completed"。
    chapters: list = field(default_factory=list)
    # 故事生命周期状态："active"（进行中，可续写）| "completed"（已完结，拒绝新决策）。
    status: str = "active"

    def open_chapter(self) -> Chapter:
        """返回当前正在写入的 open 章；不存在则创建（首章或上一章收束后开新章）。

        全书无任何章节（老/迁移故事）时回落创建第 1 章，覆盖既有全部段落。
        """
        if self.chapters:
            last = self.chapters[-1]
            if last.status == "open":
                return last
        no = (self.chapters[-1].no + 1) if self.chapters else 1
        ch = Chapter(no=no,
                     passage_from=1 if not self.chapters else len(self.passages) + 1,
                     passage_to=len(self.passages))
        self.chapters.append(ch)
        return ch

    def current_chapter(self) -> Chapter:
        """当前正在写入的章（open 章或最后一次创建的章）。"""
        return self.open_chapter()

    def close_chapter(self, title: str, *, is_final: bool = False) -> Chapter:
        """把当前 open 章收束：置 closed、写标题与收束段落号；此后自动开下一章（结局章除外）。"""
        ch = self.open_chapter()
        ch.status = "closed"
        ch.is_final = is_final
        if title:
            ch.title = title
        ch.passage_to = len(self.passages)
        if not is_final:
            self.open_chapter()  # 为下一拍预开新章
        return ch

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
            "synopsis_checked": story.synopsis_checked,
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
            "foreshadows": story.foreshadows, "relations": story.relations,
            "timeline": story.timeline, "grounding": story.grounding,
            "retrieval_profile": story.retrieval_profile,
            "genre": story.genre or (story.retrieval_profile or {}).get("genre", ""),
            "chapters": [
                {"no": c.no, "title": c.title, "passage_from": c.passage_from,
                 "passage_to": c.passage_to, "is_final": c.is_final,
                 "summary": c.summary, "status": c.status}
                for c in story.chapters
            ],
            "status": story.status,
        }

    def delete(self, story_id: str) -> bool:
        return self._data.pop(story_id, None) is not None

    def import_snapshot(self, data: dict) -> Story:
        import uuid

        story = Story(
            id=str(uuid.uuid4()),
            premise=data.get("premise", ""),
            synopsis=data.get("synopsis", "") or "",
            synopsis_checked=data.get("synopsis_checked") or {},
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
            relations=data.get("relations") or [],
            timeline=data.get("timeline") or [],
            grounding=data.get("grounding") or [],
            retrieval_profile=data.get("retrieval_profile") or {},
            genre=data.get("genre") or "",
            status=data.get("status") or "active",
        )
        story.chapters = [
            Chapter(
                no=int(c.get("no") or (i + 1)),
                title=c.get("title") or "",
                passage_from=int(c.get("passage_from") or 0),
                passage_to=int(c.get("passage_to") or 0),
                is_final=bool(c.get("is_final", False)),
                summary=c.get("summary") or "",
                status=c.get("status") or "closed",
            )
            for i, c in enumerate(data.get("chapters") or [])
        ]
        if not story.chapters:
            story.open_chapter()
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
                "status": s.status,
            }
            for s in reversed(list(self._data.values()))
        ]

    def reset(self) -> None:
        self._data.clear()