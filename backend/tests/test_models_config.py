from fastapi.testclient import TestClient

from app.main import app
from app.services import registry


def _client():
    return TestClient(app)


def test_models_config_initial_is_mock():
    r = _client().get("/v1/models/config")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "mock"
    assert body["configured"] is False
    assert body["api_key_set"] is False


def test_set_and_get_model_config():
    c = _client()
    r = c.post("/v1/models/config", json={
        "provider": "deepseek", "model": "deepseek-chat", "api_key": "sk-test",
        "base_url": "https://api.deepseek.com/v1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "openai-compat"
    assert body["configured"] is True
    assert body["api_key_set"] is True
    assert body["model"] == "deepseek-chat"
    assert "sk-test" not in body  # Key 不回传明文

    # gateway 实读生效
    assert registry.gateway.resolve()["api_key"] == "sk-test"


def test_default_base_url_filled():
    c = _client()
    body = c.post("/v1/models/config", json={"provider": "ollama", "model": "qwen2.5"}).json()
    assert body["base_url"].startswith("http")  # 自动补齐本地默认地址
    assert body["mode"] == "openai-compat"


def test_clear_returns_to_mock():
    c = _client()
    c.post("/v1/models/config", json={"provider": "openai", "model": "gpt-4o-mini", "api_key": "x"})
    r = c.post("/v1/models/config/clear")
    body = r.json()
    assert body["configured"] is False
    assert body["mode"] == "mock"