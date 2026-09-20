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
from pathlib import Path

from app.schemas import Card, DirectionSpec
from app.services.store import Decision, Story, StoryNotFound

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    premise TEXT NOT NULL,
    synopsis TEXT NOT NULL DEFAULT '',
    next_decision_no INTEGER NOT NULL DEFAULT 1
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
    PRIMARY KEY (story_id, no)
);
CREATE INDEX IF NOT EXISTS idx_passages_story ON passages(story_id);
CREATE INDEX IF NOT EXISTS idx_decisions_story ON decisions(story_id);
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
    return d


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

    def init(self) -> None:
        """幂等建表（构造时已执行，保留以显式调用）。"""
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def _insert_decision(self, story_id: str, d: Decision) -> None:
        self._conn.execute(
            """INSERT INTO decisions(story_id,no,pool_version,mode,card_id,applied,cards_json,direction_json)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(story_id,no) DO UPDATE SET
                 pool_version=excluded.pool_version, mode=excluded.mode, card_id=excluded.card_id,
                 applied=excluded.applied, cards_json=excluded.cards_json,
                 direction_json=excluded.direction_json""",
            _decision_to_row(story_id, d),
        )

    def save(self, story: Story) -> Story:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO stories(id,premise,synopsis,next_decision_no) VALUES(?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET premise=excluded.premise,
                     synopsis=excluded.synopsis, next_decision_no=excluded.next_decision_no""",
                (story.id, story.premise, story.synopsis, story.next_decision_no),
            )
            self._conn.execute("DELETE FROM passages WHERE story_id=?", (story.id,))
            self._conn.executemany(
                """INSERT INTO passages(story_id,no,decision_no,content) VALUES(?,?,?,?)""",
                [(story.id, p["no"], p.get("decision_no"), p["content"]) for p in story.passages],
            )
            self._conn.execute("DELETE FROM decisions WHERE story_id=?", (story.id,))
            for d in story.decisions.values():
                self._insert_decision(story.id, d)
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
            story = Story(
                id=row["id"], premise=row["premise"], synopsis=row["synopsis"],
                next_decision_no=row["next_decision_no"],
                passages=[{"no": p["no"], "decision_no": p["decision_no"], "content": p["content"]}
                          for p in passages],
                decisions={d.no: d for d in (_row_to_decision(r) for r in decision_rows)},
            )
            self._cache[story_id] = story
            return story

    def reset(self) -> None:
        """清空内存缓存与数据库（测试/维护用）。"""
        with self._lock:
            self._cache.clear()
            self._conn.execute("DELETE FROM passages")
            self._conn.execute("DELETE FROM decisions")
            self._conn.execute("DELETE FROM stories")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()