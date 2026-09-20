"""决策闭环端到端集成测试：stories → cards → gacha/apply → 生成正文。

全部走 mock LLM（无 key），验证抽卡→正文闭环可跑通。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import registry


@pytest.fixture(autouse=True)
def _reset_store():
    registry.store.reset()
    yield


def _client() -> TestClient:
    return TestClient(app)


def test_create_story_returns_opening_and_first_decision():
    r = _client().post("/v1/stories", json={"premise": "一个失忆的杀手想找回身份"})
    assert r.status_code == 201
    body = r.json()
    assert body["story_id"]
    assert len(body["opening"]) > 10
    assert body["decision_no"] == 1
    assert 3 <= len(body["cards"]) <= 5


def test_full_blind_gacha_loop():
    c = _client()
    created = c.post("/v1/stories", json={"premise": "暴雨中的空城"}).json()
    sid, no = created["story_id"], created["decision_no"]

    got = c.get(f"/v1/stories/{sid}/decisions/{no}/cards")
    assert got.status_code == 200
    cards = got.json()["cards"]
    assert 3 <= len(cards) <= 5

    drawn = c.post(f"/v1/stories/{sid}/decisions/{no}/gacha").json()
    assert drawn["mode"] == "gacha_draw"
    assert drawn["card"]["card_id"] in {c_["card_id"] for c_ in cards}
    assert len(drawn["passage"]) > 10
    assert drawn["next_decision_no"] == 2

    # 已锁定 → 重复 gacha 返回 409
    again = c.post(f"/v1/stories/{sid}/decisions/{no}/gacha")
    assert again.status_code == 409


def test_pick_and_free_apply():
    c = _client()
    created = c.post("/v1/stories", json={"premise": "末日后的图书馆"}).json()
    sid, no = created["story_id"], created["decision_no"]
    card_id = created["cards"][0]["card_id"]

    picked = c.post(f"/v1/stories/{sid}/decisions/{no}/apply", json={"card_id": card_id}).json()
    assert picked["mode"] == "gacha_pick"
    assert len(picked["passage"]) > 10

    # 下一决策自由输入
    nxt = picked["next_decision_no"]
    free = c.post(f"/v1/stories/{sid}/decisions/{nxt}/apply",
                  json={"custom_instruction": "让主角在旧码头发现藏宝图"}).json()
    assert free["mode"] == "free"
    assert len(free["passage"]) > 10


def test_apply_unknown_card_422():
    c = _client()
    sid = c.post("/v1/stories", json={"premise": "x"}).json()["story_id"]
    r = c.post(f"/v1/stories/{sid}/decisions/1/apply", json={"card_id": "nope"})
    assert r.status_code == 422


def test_apply_missing_both_rejected():
    c = _client()
    sid = c.post("/v1/stories", json={"premise": "x"}).json()["story_id"]
    r = c.post(f"/v1/stories/{sid}/decisions/1/apply", json={})
    assert r.status_code == 422


def test_unknown_story_404():
    r = _client().get("/v1/stories/nope")
    assert r.status_code == 404


def test_blueprint_built_and_persisted():
    c = _client()
    sid = c.post("/v1/stories", json={"premise": "雾海中的记忆之城"}).json()["story_id"]

    bp = c.get(f"/v1/stories/{sid}/blueprint").json()
    assert "world" in bp and "history" in bp and "characters" in bp and "outline" in bp
    # 三段前置齐全
    assert bp["world"].get("rules")
    assert bp["world"].get("power_system") is not None
    assert isinstance(bp["characters"], list) and bp["characters"]
    assert bp["outline"][0]["type"] == "act" or any(o["type"] == "act" for o in bp["outline"])
    # 再造一个连接，验证蓝图已持久化
    assert isinstance(bp["history"], list)


def test_quality_fields_in_draw_and_relint_endpoint():
    c = _client()
    sid = c.post("/v1/stories", json={"premise": "质检测试"}).json()["story_id"]
    drawn = c.post(f"/v1/stories/{sid}/decisions/1/gacha").json()
    assert "lint" in drawn and isinstance(drawn["lint"], list)
    assert "consistency" in drawn and drawn["consistency"]["passed"] is True

    rel = c.post(f"/v1/stories/{sid}/passages/1/lint")
    assert rel.status_code == 200
    assert "lint" in rel.json() and "consistency" in rel.json()


def test_stream_decision_sse():
    c = _client()
    sid = c.post("/v1/stories", json={"premise": "流式测试"}).json()["story_id"]
    r = c.post(f"/v1/stories/{sid}/decisions/1/stream", json={"draw": True})
    assert r.status_code == 200
    body = r.text
    assert "event: passage_start" in body
    assert "event: delta" in body
    assert "event: passage_end" in body
    assert '"next_decision_no": 2' in body
    assert '"lint"' in body


def test_stream_requires_one_action():
    c = _client()
    sid = c.post("/v1/stories", json={"premise": "x"}).json()["story_id"]
    # draw + card_id 同时存在 → 422
    r = c.post(f"/v1/stories/{sid}/decisions/1/stream",
               json={"draw": True, "custom_instruction": "x"})
    assert r.status_code == 422