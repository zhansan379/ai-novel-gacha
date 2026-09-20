"""运行时模型接入配置（Keychain）：支持前端动态配置 API Key，持久化到 SQLite（重启不丢）。

优先级：Keychain 运行时配置 > 环境变量/.env（settings.api_keys）。
提供了各厂商默认 Base URL，未填时自动补齐。
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_PRELOAD_BASES = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "moonshot": "https://api.moonshot.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://localhost:11434/v1",
}

_TABLES = """
CREATE TABLE IF NOT EXISTS keychain(
    provider TEXT PRIMARY KEY,
    model TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS config(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def default_base_url(provider: str) -> str:
    return _PRELOAD_BASES.get(provider, "")


class Keychain:
    def __init__(self, db_path: str) -> None:
        self._lock = threading.RLock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_TABLES)
        self._conn.commit()

    def save(self, *, provider: str, model: str, base_url: str = "", api_key: str = "") -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO keychain(provider, model, base_url, api_key)
                   VALUES(?,?,?,?)
                   ON CONFLICT(provider) DO UPDATE SET
                     model=excluded.model, base_url=excluded.base_url, api_key=excluded.api_key""",
                (provider, model, base_url, api_key),
            )
            self._conn.execute(
                "INSERT INTO config(key, value) VALUES('active_provider', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (provider,),
            )
            self._conn.commit()

    def current(self) -> dict | None:
        """返回当前生效的运行时配置；未配置返回 None。"""
        with self._lock:
            row = self._conn.execute("SELECT value FROM config WHERE key='active_provider'").fetchone()
            if not row:
                return None
            provider = row[0]
            kr = self._conn.execute("SELECT * FROM keychain WHERE provider=?", (provider,)).fetchone()
            if not kr:
                return None
            return {"provider": provider, "model": kr[1], "base_url": kr[2], "api_key": kr[3]}

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM keychain")
            self._conn.execute("DELETE FROM config")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()