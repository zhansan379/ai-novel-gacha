"""SQLite 持久化 StoryStore（写透 + 内存工作缓存）。

- 接口与内存版一致：get(sync) / save(sync) / reset(sync)。
- save 每次把整本 Story 序列化落库（stories / passages / decisions），get 命中缓存否则从库重建。
- 单连接 + threading.Lock 串行化，避免并发写；小数据库对 MVP 足够。
- Story / Decision 以 JSON 列存 cards / direction_spec，保证后续加字段向兼容。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path

from app.schemas import Card, DirectionSpec
from app.services.store import Chapter, Decision, Story, StoryNotFound, flatten_world

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    premise TEXT NOT NULL,
    synopsis TEXT NOT NULL DEFAULT '',
    next_decision_no INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id TEXT NOT NULL,
    no INTEGER NOT NULL,
    decision_no INTEGER,
    content TEXT NOT NULL,
    UNIQUE(story_id, no)
);
CREATE TABLE IF NOT EXISTS decisions (
    story_id TEXT NOT NULL,
    no INTEGER NOT NULL,
    pool_version INTEGER NOT NULL DEFAULT 1,
    mode TEXT,
    card_id TEXT,
    applied INTEGER NOT NULL DEFAULT 0,
    cards_json TEXT NOT NULL DEFAULT '[]',
    direction_json TEXT,
    rollback_json TEXT,
    PRIMARY KEY (story_id, no)
);
CREATE TABLE IF NOT EXISTS chapters (
    story_id TEXT NOT NULL,
    no INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    passage_from INTEGER NOT NULL,
    passage_to INTEGER NOT NULL,
    is_final INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'closed',
    PRIMARY KEY (story_id, no)
);
CREATE INDEX IF NOT EXISTS idx_passages_story ON passages(story_id);
CREATE INDEX IF NOT EXISTS idx_decisions_story ON decisions(story_id);
CREATE INDEX IF NOT EXISTS idx_chapters_story ON chapters(story_id);
"""


def _card_json(cards: list[Card]) -> str:
    return json.dumps([c.model_dump(mode="json") for c in cards], ensure_ascii=False)


def _cards_from_json(text: str) -> list[Card]:
    data = json.loads(text)
    return [Card.model_validate(obj) for obj in data]


def _decision_to_row(story_id: str, d: Decision) -> tuple:
    return (
        story_id, d.no, d.pool_version, d.mode, d.card_id, int(d.applied),
        _card_json(d.cards),
        d.direction_spec.model_dump_json() if d.direction_spec else None,
        json.dumps(d.rollback, ensure_ascii=False) if d.rollback else None,
    )


def _row_to_decision(row: sqlite3.Row) -> Decision:
    d = Decision(
        no=row["no"],
        pool_version=row["pool_version"],
        mode=row["mode"],
        card_id=row["card_id"],
        applied=bool(row["applied"]),
        cards=_cards_from_json(row["cards_json"]),
    )
    if row["direction_json"]:
        d.direction_spec = DirectionSpec.model_validate_json(row["direction_json"])
    if row["rollback_json"]:
        try:
            d.rollback = json.loads(row["rollback_json"])
        except json.JSONDecodeError:
            d.rollback = None
    return d


def _blueprint_json(story: Story) -> str:
    return json.dumps({
        "world": story.world, "history": story.history,
        "characters": story.characters, "appearances": story.appearances,
        "style": story.style_profile_id,
        "foreshadows": story.foreshadows, "relations": story.relations,
        "timeline": story.timeline, "grounding": story.grounding,
        "retrieval_profile": story.retrieval_profile,
        "genre": story.genre,
    }, ensure_ascii=False)


def _genre_from_meta(text: str | None) -> str:
    """从 blueprint_json 元数据里取题材（书架列表用，不完整/解析失败则空串）。"""
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if isinstance(data, dict):
        return str(data.get("genre") or (data.get("retrieval_profile") or {}).get("genre") or "")
    return ""


def _fill_blueprint(story: Story, text: str | None) -> None:
    if not text:
        return
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    if isinstance(data, dict):
        story.world = flatten_world(data.get("world") or {})
        story.history = data.get("history") or []
        story.characters = data.get("characters") or []
        story.appearances = data.get("appearances") or []
        story.foreshadows = data.get("foreshadows") or []
        story.relations = data.get("relations") or []
        story.grounding = data.get("grounding") or []
        story.timeline = data.get("timeline") or []
        story.retrieval_profile = data.get("retrieval_profile") or {}
        story.genre = data.get("genre") or (story.retrieval_profile or {}).get("genre", "")
        if data.get("style"):
            story.style_profile_id = data["style"]


def _chapter_to_row(story_id: str, c: Chapter) -> tuple:
    return (story_id, c.no, c.title, c.passage_from, c.passage_to,
            int(c.is_final), c.summary, c.status)


def _row_to_chapter(row: sqlite3.Row) -> Chapter:
    return Chapter(
        no=row["no"], title=row["title"],
        passage_from=row["passage_from"], passage_to=row["passage_to"],
        is_final=bool(row["is_final"]), summary=row["summary"], status=row["status"],
    )


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._lock = threading.RLock()
        self._cache: dict[str, Story] = {}
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """轻量列迁移：为既有库补充 blueprint_json / decisions.rollback_json / stories.user_id。"""
        with self._lock:
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info(stories)").fetchall()]
            if "blueprint_json" not in cols:
                self._conn.execute("ALTER TABLE stories ADD COLUMN blueprint_json TEXT")
            if "status" not in cols:
                self._conn.execute("ALTER TABLE stories ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            if "user_id" not in cols:
                self._conn.execute("ALTER TABLE stories ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
            chcols = [r[1] for r in self._conn.execute("PRAGMA table_info(chapters)").fetchall()]
            if "summary" not in chcols:
                self._conn.execute("ALTER TABLE chapters ADD COLUMN summary TEXT NOT NULL DEFAULT ''")
            if "status" not in chcols:
                self._conn.execute("ALTER TABLE chapters ADD COLUMN status TEXT NOT NULL DEFAULT 'closed'")
            dcols = [r[1] for r in self._conn.execute("PRAGMA table_info(decisions)").fetchall()]
            if "rollback_json" not in dcols:
                self._conn.execute("ALTER TABLE decisions ADD COLUMN rollback_json TEXT")
            self._conn.commit()

    def init(self) -> None:
        """幂等建表（构造时已执行，保留以显式调用）。"""
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def _insert_decision(self, story_id: str, d: Decision) -> None:
        self._conn.execute(
            """INSERT INTO decisions(story_id,no,pool_version,mode,card_id,applied,cards_json,direction_json,rollback_json)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(story_id,no) DO UPDATE SET
                 pool_version=excluded.pool_version, mode=excluded.mode, card_id=excluded.card_id,
                 applied=excluded.applied, cards_json=excluded.cards_json,
                 direction_json=excluded.direction_json, rollback_json=excluded.rollback_json""",
            _decision_to_row(story_id, d),
        )

    def save(self, story: Story) -> Story:
        with self._lock:
            self._conn.execute(
                """INSERT INTO stories(id,user_id,premise,synopsis,next_decision_no,blueprint_json,status)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET user_id=excluded.user_id,
                     premise=excluded.premise, synopsis=excluded.synopsis,
                     next_decision_no=excluded.next_decision_no,
                     blueprint_json=excluded.blueprint_json, status=excluded.status""",
                (story.id, story.user_id or "", story.premise, story.synopsis,
                 story.next_decision_no, _blueprint_json(story), story.status),
            )
            self._conn.execute("DELETE FROM passages WHERE story_id=?", (story.id,))
            self._conn.executemany(
                """INSERT INTO passages(story_id,no,decision_no,content) VALUES(?,?,?,?)""",
                [(story.id, p["no"], p.get("decision_no"), p["content"]) for p in story.passages],
            )
            self._conn.execute("DELETE FROM decisions WHERE story_id=?", (story.id,))
            for d in story.decisions.values():
                self._insert_decision(story.id, d)
            self._conn.execute("DELETE FROM chapters WHERE story_id=?", (story.id,))
            self._conn.executemany(
                """INSERT INTO chapters(story_id,no,title,passage_from,passage_to,is_final,summary,status)
                   VALUES(?,?,?,?,?,?,?,?)""",
                [_chapter_to_row(story.id, c) for c in story.chapters],
            )
            self._conn.commit()
            self._cache[story.id] = story
            return story

    def get(self, story_id: str) -> Story:
        with self._lock:
            cached = self._cache.get(story_id)
            if cached is not None:
                return cached
            row = self._conn.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone()
            if row is None:
                raise StoryNotFound(story_id)
            passages = self._conn.execute(
                "SELECT no, decision_no, content FROM passages WHERE story_id=? ORDER BY no",
                (story_id,),
            ).fetchall()
            decision_rows = self._conn.execute(
                "SELECT * FROM decisions WHERE story_id=? ORDER BY no", (story_id,),
            ).fetchall()
            chapter_rows = self._conn.execute(
                "SELECT * FROM chapters WHERE story_id=? ORDER BY no", (story_id,),
            ).fetchall()
            story = Story(
                id=row["id"], premise=row["premise"], synopsis=row["synopsis"],
                user_id=row["user_id"] or "",
                next_decision_no=row["next_decision_no"], status=row["status"] or "active",
                passages=[{"no": p["no"], "decision_no": p["decision_no"], "content": p["content"]}
                          for p in passages],
                decisions={d.no: d for d in (_row_to_decision(r) for r in decision_rows)},
                chapters=[_row_to_chapter(r) for r in chapter_rows],
            )
            if not story.chapters:
                story.open_chapter()
            _fill_blueprint(story, row["blueprint_json"])
            self._cache[story_id] = story
            return story

    def list(self, user_id: str = "") -> list[dict]:
        """返回某用户故事的精简概览（书架用），按创建先后倒序。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT rowid AS rid, id, premise, synopsis, next_decision_no, status, blueprint_json "
                "FROM stories WHERE user_id=? ORDER BY rid DESC",
                (user_id,),
            ).fetchall()
            return [
                {
                    "story_id": r["id"],
                    "premise": r["premise"],
                    "synopsis": r["synopsis"],
                    "next_decision_no": r["next_decision_no"],
                    "status": r["status"] or "active",
                    "genre": _genre_from_meta(r["blueprint_json"]),
                }
                for r in rows
            ]

    def snapshot(self, story_id: str) -> dict:
        """导出整本故事的可移植快照（往返导入用），与 save 持久化的字段一致。"""
        with self._lock:
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
                "appearances": story.appearances,
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
        """删除故事及其正文/决策；不存在返回 False。"""
        with self._lock:
            self._cache.pop(story_id, None)
            cur = self._conn.execute("DELETE FROM stories WHERE id=?", (story_id,))
            self._conn.execute("DELETE FROM passages WHERE story_id=?", (story_id,))
            self._conn.execute("DELETE FROM decisions WHERE story_id=?", (story_id,))
            self._conn.execute("DELETE FROM chapters WHERE story_id=?", (story_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def import_snapshot(self, data: dict, user_id: str = "") -> Story:
        """从快照重建一本新故事（分配新 id，避免覆盖既有同 id 书籍），归属 user_id。"""
        with self._lock:
            story = Story(
                id=str(uuid.uuid4()),
                user_id=user_id or "",
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
                appearances=data.get("appearances") or [],
                style_profile_id=data.get("style_profile_id") or "restrained",
                foreshadows=data.get("foreshadows") or [],
                timeline=data.get("timeline") or [],
                grounding=data.get("grounding") or [],
                status=data.get("status") or "active",
            )
            story.chapters = [
                Chapter(
                    no=int(c.get("no") or (i + 1)), title=c.get("title") or "",
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
            self.save(story)
            return story

    def reset(self) -> None:
        """清空内存缓存与数据库（测试/维护用）。"""
        with self._lock:
            self._cache.clear()
            self._conn.execute("DELETE FROM passages")
            self._conn.execute("DELETE FROM decisions")
            self._conn.execute("DELETE FROM chapters")
            self._conn.execute("DELETE FROM stories")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()