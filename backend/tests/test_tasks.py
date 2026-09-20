"""异步开书任务：提交返回 task_id、轮询终态取 result、失败进 error、未知任务 404。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.llm import LLMGateway
from app.llm.errors import LLMError
from app.services import registry

# 复用 test_api_flow 的确定性桩，避免重复维护样板（pytest prepend 模式下同可导入）
from test_api_flow import _stub_complete, _stub_stream  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_gateway(monkeypatch):
    registry.store.reset()
    registry.tasks.reset()
    monkeypatch.setattr(LLMGateway, "complete", _stub_complete)
    monkeypatch.setattr(LLMGateway, "stream", _stub_stream)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _poll_status(client: TestClient, task_id: str) -> dict:
    r = client.get(f"/v1/stories/tasks/{task_id}")
    assert r.status_code == 200, r.text
    return r.json()


def test_submit_returns_task_id_pending_and_reaches_done(client):
    r = client.post("/v1/stories", json={"premise": "雾海记忆城"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    task_id = body["task_id"]
    assert task_id

    # 轮询几次即可到 done（桩同步完成；真机则以阶段推进）
    for _ in range(40):
        st = _poll_status(client, task_id)
        if st["status"] == "done":
            break
        if st["status"] == "error":
            raise AssertionError(f"任务失败: {st['error']}")
    assert st["status"] == "done"
    result = st["result"]
    assert result["story_id"] and result["opening"]
    assert result["decision_no"] == 1 and 3 <= len(result["cards"]) <= 5


def test_unknown_task_id_404(client):
    r = client.get("/v1/stories/tasks/does-not-exist")
    assert r.status_code == 404


def test_task_error_surface_via_status(client, monkeypatch):
    async def broken_complete(self, *, task, system, user, max_tokens=None, temperature=None):
        if task == "init":
            raise LLMError("模型不可达")
        return await _stub_complete(self, task=task, system=system, user=user,
                                    max_tokens=max_tokens, temperature=temperature)

    monkeypatch.setattr(LLMGateway, "complete", broken_complete)

    task_id = client.post("/v1/stories", json={"premise": "雾海记忆城"}).json()["task_id"]
    for _ in range(40):
        st = _poll_status(client, task_id)
        if st["status"] == "error":
            break
    assert st["status"] == "error"
    assert st["error"]["code"] == "MODEL_ERROR"
    # 失败不落库
    assert registry.store.list() == []


def test_multiple_parallel_tasks_all_complete(client):
    """多本书并行开书：各自能独立到 done（信号量不堵死）。"""
    ids = [client.post("/v1/stories", json={"premise": f"书{i}"}).json()["task_id"] for i in range(5)]
    fora = {tid: _poll_status(client, tid) for tid in ids}
    for _ in range(80):
        if all(s["status"] == "done" for s in fora.values()):
            break
        for tid in ids:
            fora[tid] = _poll_status(client, tid)
    assert all(s["status"] == "done" for s in fora.values())
    assert all(s["result"]["story_id"] for s in fora.values())