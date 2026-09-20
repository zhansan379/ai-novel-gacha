from fastapi.testclient import TestClient

from app.main import app


def test_health():
    client = TestClient(app)
    res = client.get("/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "app" in body  # 当前 LLM 运行模式（mock / openai-compat）