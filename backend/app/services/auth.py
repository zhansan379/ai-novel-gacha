"""用户认证（轻量）：注册 / 登录 / 登出，令牌会话。

- `users`：用户名（唯一）+ 密码哈希（PBKDF2 + 随机盐）。不存明文密码。
- `sessions`：随机 token → user_id。前端持有 token，请求带 `Authorization: Bearer <token>`。
- 无 JWT/缓存/第三方依赖，单进程够用，符合"公网轻量化多用户"目标。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from pathlib import Path

_TOKEN_TTL = 30 * 24 * 3600  # 会话 30 天，过期懒清理

_TABLES = """
CREATE TABLE IF NOT EXISTS users(
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    pass_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE TABLE IF NOT EXISTS sessions(
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""

_ITERATIONS = 200_000


class AuthError(Exception):
    pass


class UsernameTaken(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    ).hex()


class AuthManager:
    def __init__(self, db_path: str) -> None:
        self._lock = threading.RLock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_TABLES)
        self._conn.commit()

    def register(self, username: str, password: str) -> str:
        """创建用户，返回 user_id。用户名重复抛 UsernameTaken。"""
        username = (username or "").strip()
        if not username or len(username) > 40:
            raise InvalidCredentials("用户名需为 1-40 字符")
        if len(password) < 6:
            raise InvalidCredentials("密码至少 6 位")
        with self._lock:
            exists = self._conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
            if exists:
                raise UsernameTaken("该用户名已被占用")
            user_id = secrets.token_hex(16)
            salt = secrets.token_hex(16)
            self._conn.execute(
                "INSERT INTO users(id, username, pass_hash, salt, created_at) VALUES(?,?,?,?,?)",
                (user_id, username, _hash(password, salt), salt, time.time()),
            )
            self._conn.commit()
            return user_id

    def login(self, username: str, password: str) -> str:
        """用户名密码校验通过则签发会话 token。失败抛 InvalidCredentials。"""
        username = (username or "").strip()
        with self._lock:
            row = self._conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if row is None:
                raise InvalidCredentials("用户名或密码错误")
            expected = _hash(password or "", row["salt"])
            if not hmac.compare_digest(expected, row["pass_hash"]):
                raise InvalidCredentials("用户名或密码错误")
            token = secrets.token_hex(32)
            self._conn.execute(
                "INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
                (token, row["id"], time.time()),
            )
            self._conn.commit()
            self._purge_sessions()
            return token

    def logout(self, token: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            self._conn.commit()

    def user_for_token(self, token: str) -> str | None:
        """令牌有效则返回 user_id，否则 None。顺带清理过期会话。"""
        if not token:
            return None
        with self._lock:
            row = self._conn.execute("SELECT user_id, created_at FROM sessions WHERE token=?", (token,)).fetchone()
            if row is None:
                return None
            if time.time() - row["created_at"] > _TOKEN_TTL:
                self._conn.execute("DELETE FROM sessions WHERE token=?", (token,))
                self._conn.commit()
                return None
            return row["user_id"]

    def username_of(self, user_id: str) -> str:
        with self._lock:
            row = self._conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
            return row["username"] if row else ""

    def _purge_sessions(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE created_at < ?", (time.time() - _TOKEN_TTL,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()