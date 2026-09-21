"""用户认证与归属隔离：真实 token 路径（覆盖 test_auth_probe 之外的鉴权逻辑）。

通过移除 conftest 的依赖覆写，这里用真实头 `Authorization: Bearer <token>` 走完整链路：
注册 → 登录 → me → 无 token 401 → 越权访问他人故事 404 → 登出后 token 失效。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import get_current_user
from app.services import registry
from app.services.store import Story


def _use_real_auth():
    """启用真实鉴权：移除 conftest 的 probe 依赖覆写，必须在本测试体内调用。"""
    app.dependency_overrides.pop(get_current_user, None)
    registry.tasks.reset()


def _client():
    return TestClient(app)


def _register(client, username, password="secret123"):
    r = client.post("/v1/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth_h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me_logout():
    _use_real_auth()
    c = _client()
    _register(c, "alice")

    # 重复用户名 → 409
    dup = c.post("/v1/auth/register", json={"username": "alice", "password": "secret123"})
    assert dup.status_code == 409

    # 登录拿 token
    r = c.post("/v1/auth/login", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 200
    token = r.json()["token"]

    # me 校验 token
    assert c.get("/v1/auth/me", headers=_auth_h(token)).status_code == 200
    # 错误密码 → 401
    assert c.post("/v1/auth/login", json={"username": "alice", "password": "wrong"}).status_code == 401

    # 登出后 token 失效
    assert c.post("/v1/auth/logout", headers=_auth_h(token)).status_code == 200
    assert c.get("/v1/auth/me", headers=_auth_h(token)).status_code == 401


def test_unauthenticated_requests_rejected():
    _use_real_auth()
    c = _client()
    # 健康检查公有
    assert c.get("/v1/health").status_code == 200
    # 业务接口无 token → 401
    assert c.get("/v1/stories").status_code == 401
    assert c.post("/v1/stories", json={"premise": "x"}).status_code == 401
    assert c.get("/v1/models/config").status_code == 401


def test_story_ownership_isolation():
    _use_real_auth()
    c = _client()
    alice_token = _register(c, "alice")
    bob_token = _register(c, "bob")
    alice_uid = registry.auth.user_for_token(alice_token)  # 真实 user_id（hex，非用户名）

    # 以 alice 身份落一本书
    registry.store.save(Story(id="book-alice", premise="艾丽丝的世界", user_id=alice_uid))

    # alice 可读自己的书
    ok = c.get("/v1/stories/book-alice", headers=_auth_h(alice_token))
    assert ok.status_code == 200
    assert ok.json()["premise"] == "艾丽丝的世界"
    # alice 的书架能看到 1 本；bob 的书架看到 0 本
    assert len(c.get("/v1/stories", headers=_auth_h(alice_token)).json()["stories"]) == 1
    assert c.get("/v1/stories", headers=_auth_h(bob_token)).json()["stories"] == []

    # bob 越权访问 alice 的书 → 按不存在处理（404，不泄露存在性）
    assert c.get("/v1/stories/book-alice", headers=_auth_h(bob_token)).status_code == 404
    assert c.get("/v1/stories/book-alice/export", headers=_auth_h(bob_token)).status_code == 404

    # bob 尝试删除 alice 的书也应为 404
    assert c.delete("/v1/stories/book-alice", headers=_auth_h(bob_token)).status_code == 404