"""测试级数据库隔离：每个测试用独立的临时 SQLite DB，避免污染开发数据。"""
import pytest

from app.context import current_user_id
from app.main import app as fastapi_app
from app.api.routes import get_current_user
from app.services import registry
from app.services.auth import AuthManager
from app.services.grounding import WebSearch
from app.services.keychain import Keychain
from app.storage.sqlite import SQLiteStore

# 测试默认登录用户（DDL 后注入到独立 auth 库）
_TEST_USER = "tester"


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path):
    store = SQLiteStore(str(tmp_path / "test.db"))
    keychain = Keychain(str(tmp_path / "keychain.db"))
    registry.store = store
    registry.keychain = keychain
    registry.gateway._keychain = keychain  # gateway 换用同一 keychain
    # 隔离 ambient .env：清空网关的 env 兜底 Key，避免 backend/.env 的占位 key 污染"未配置"单测
    registry.gateway.settings.api_keys = {}
    registry.gateway.settings.base_urls = {}
    registry.story_service._store = store  # story_service 持有同一存储实例
    # 关闭联网预取：单元/集成测试不发真实网络请求（保持确定性、不拖慢开书轮询）
    registry.story_service._web = WebSearch(api_key="")
    registry.tasks.reset()  # 清空异步开书任务表，避免跨用例串状态
    yield
    store.close()
    keychain.close()


@pytest.fixture(autouse=True)
def _auth_probe(tmp_path):
    """注入一个测试用户并覆盖鉴权依赖：既有集成测试无需逐一带 token 即可通过。

    归属/鉴权本身的真实验证由 tests/test_auth.py 用真实 token 单独覆盖。
    """
    auth = AuthManager(str(tmp_path / "auth.db"))
    registry.auth = auth
    user_id = auth.register(_TEST_USER, "secret123")
    # 测试体内直接 gateway.resolve() 也应能读到当前用户（不只请求内）
    current_user_id.set(user_id)

    async def _probe():
        current_user_id.set(user_id)
        return user_id

    fastapi_app.dependency_overrides[get_current_user] = _probe
    yield
    fastapi_app.dependency_overrides.pop(get_current_user, None)
    auth.close()