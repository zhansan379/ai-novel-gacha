"""测试级数据库隔离：每个测试用独立的临时 SQLite DB，避免污染开发数据。"""
import pytest

from app.services import registry
from app.services.grounding import WebSearch
from app.services.keychain import Keychain
from app.storage.sqlite import SQLiteStore


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