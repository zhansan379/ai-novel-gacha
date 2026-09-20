"""测试级数据库隔离：每个测试用独立的临时 SQLite DB，避免污染开发数据。"""
import pytest

from app.services import registry
from app.services.keychain import Keychain
from app.storage.sqlite import SQLiteStore


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path):
    store = SQLiteStore(str(tmp_path / "test.db"))
    keychain = Keychain(str(tmp_path / "keychain.db"))
    registry.store = store
    registry.keychain = keychain
    registry.gateway._keychain = keychain  # gateway 换用同一 keychain
    registry.story_service._store = store  # story_service 持有同一存储实例
    yield
    store.close()
    keychain.close()