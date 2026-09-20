"""测试级数据库隔离：每个测试用独立的临时 SQLite DB，避免污染开发数据。"""
import pytest

from app.services import registry
from app.storage.sqlite import SQLiteStore


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path):
    store = SQLiteStore(str(tmp_path / "test.db"))
    registry.store = store
    registry.story_service._store = store  # story_service 持有同一存储实例
    yield
    store.close()