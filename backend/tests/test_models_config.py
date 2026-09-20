from fastapi.testclient import TestClient

from app.main import app
from app.services import registry


def _client():
    return TestClient(app)


def test_models_config_initial_unconfigured():
    r = _client().get("/v1/models/config")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "unconfigured"
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


def test_clear_returns_to_unconfigured():
    c = _client()
    c.post("/v1/models/config", json={"provider": "openai", "model": "gpt-4o-mini", "api_key": "x"})
    r = c.post("/v1/models/config/clear")
    body = r.json()
    assert body["configured"] is False
    assert body["mode"] == "unconfigured"


def test_custom_provider_persists():
    """非预设厂商名 + 自填 Base URL 应被 Keychain 原样持久化并可回读。"""
    c = _client()
    body = c.post("/v1/models/config", json={
        "provider": "my-gateway", "model": "local-llamax",
        "base_url": "https://gw.internal:8443/v1", "api_key": "sk-custom",
    }).json()
    assert body["configured"] is True
    assert body["mode"] == "openai-compat"
    assert body["provider"] == "my-gateway"
    assert body["base_url"] == "https://gw.internal:8443/v1"

    resolved = registry.gateway.resolve()
    assert resolved["provider"] == "my-gateway"
    assert resolved["base_url"] == "https://gw.internal:8443/v1"
    assert resolved["model"] == "local-llamax"
    assert resolved["api_key"] == "sk-custom"