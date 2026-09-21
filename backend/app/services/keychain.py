"""运行时模型接入配置（Keychain）：支持前端动态配置 API Key，按用户隔离，持久化到 SQLite。

- 每个 user_id 一套模型配置；`current(user_id)` 取该用户的生效配置。
- API Key 在 `secret_key` 存在时用 Fernet 对称加密落地，读取时解密；无 secret_key
  （仅限本机/可信内网）回退明文存储，公网务必配置 SECRET_KEY。
- 提供各厂商默认 Base URL，未填时自动补齐。
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
    user_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, provider)
);
"""


def default_base_url(provider: str) -> str:
    return _PRELOAD_BASES.get(provider, "")


def _fernet(secret_key: str):
    try:
        from cryptography.fernet import Fernet
    except ImportError:  # 未安装 cryptography 时禁止加密路径
        raise RuntimeError("配置了 SECRET_KEY 但未安装 cryptography 依赖") from None
    if len(secret_key) < 32:
        raise ValueError("SECRET_KEY 需至少 32 字符（建议用 `cryptography.fernet.Fernet.generate_key()` 生成）")
    # 把任意字符串 SEnS 确定性地派生为合法 Fernet key（sha256→32 字节→urlsafe b64）
    import base64
    import hashlib
    raw = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


class Keychain:
    def __init__(self, db_path: str, secret_key: str = "") -> None:
        self._lock = threading.RLock()
        self._secret_key = secret_key
        self._fernet = _fernet(secret_key) if secret_key else None
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_TABLES)
        self._conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """把旧的单用户 keychain 表迁移为按 user 的形态（旧全局配置归入空 user_id 兜底，不丢）。"""
        with self._lock:
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info(keychain)").fetchall()]
            if "user_id" not in cols:
                # 旧表：provider PK。重建为 (user_id, provider)，旧行归入 user_id=''（env 兜底用）。
                self._conn.executescript("""
                    ALTER TABLE keychain RENAME TO keychain_legacy;
                    CREATE TABLE keychain(
                        user_id TEXT NOT NULL DEFAULT '',
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL DEFAULT '',
                        base_url TEXT NOT NULL DEFAULT '',
                        api_key TEXT NOT NULL DEFAULT '',
                        is_active INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, provider)
                    );
                    INSERT INTO keychain(user_id, provider, model, base_url, api_key, is_active)
                        SELECT '', provider, model, base_url, api_key, 1 FROM keychain_legacy;
                """)
                self._conn.commit()
            # 已有的 is_active 列无需处理；老表经上面重建已含。

    def _encrypt(self, api_key: str) -> tuple[str, bool]:
        """返回 (存储值, 是否加密)。未配置 secret_key 一律明文。"""
        if not self._fernet:
            return api_key, False
        return self._fernet.encrypt(api_key.encode("utf-8")).decode(), True

    def _decrypt(self, value: str) -> str:
        if not self._fernet or not value:
            return value
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""  # 解密失败（密钥更换等）视为未配置，避免崩溃并提示重新接入

    def save(self, *, user_id: str, provider: str, model: str,
             base_url: str = "", api_key: str = "") -> None:
        """保存该用户的一套模型配置，并将其设为该用户当前生效；同一用户其它配置取消生效。"""
        with self._lock:
            self._conn.execute(
                "UPDATE keychain SET is_active=0 WHERE user_id=?",
                (user_id,),
            )
            self._conn.execute(
                """INSERT INTO keychain(user_id, provider, model, base_url, api_key, is_active)
                   VALUES(?,?,?,?,?,1)
                   ON CONFLICT(user_id, provider) DO UPDATE SET
                     model=excluded.model, base_url=excluded.base_url,
                     api_key=excluded.api_key, is_active=1""",
                (user_id, provider, model, base_url, self._encrypt(api_key)[0]),
            )
            self._conn.commit()

    def current(self, user_id: str) -> dict | None:
        """返回该用户当前生效的运行时配置；未配置返回 None。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM keychain WHERE user_id=? AND is_active=1", (user_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "provider": row["provider"], "model": row["model"],
                "base_url": row["base_url"], "api_key": self._decrypt(row["api_key"]),
            }

    def clear(self, user_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM keychain WHERE user_id=?", (user_id,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()