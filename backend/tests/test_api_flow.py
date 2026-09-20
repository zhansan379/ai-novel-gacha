"""决策闭环端到端集成测试：stories → cards → gacha/apply → 生成正文。

运行时不再有 mock 降级，因此这里对 LLMGateway.complete/stream 注入测试桩，
用确定性内容驱动整条链路，验证抽卡→正文闭环可跑通（不依赖任何真实模型）。
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.llm import LLMGateway
from app.services import registry

_STUB_CARDS = [
    {"card_id": "t-a", "title": "夜雨敲门", "label": "EVENT", "rarity": "R", "weight": 40,
     "content": "雨夜有人敲门，指名要找主角。"},
    {"card_id": "t-b", "title": "落魄画师", "label": "MEETING", "rarity": "SR", "weight": 25,
     "content": "画师认出了主角身上的一件旧物。",
     "risk_balance": {"tension": 6, "suggested_turn": "画师揭晓关于主角过去的线索"}},
    {"card_id": "t-c", "title": "无名密信", "label": "FORESHADOW", "rarity": "N", "weight": 60,
     "content": "一封没有落款的信，笔迹却异常熟悉。"},
]

_STUB_BLUEPRINT = {
    "world": {"rules": ["魔法受七日蚀月周期影响"], "geography": "雾海旧城",
              "power_system": "记忆刻印", "factions": ["守刻人"], "constraints": ["刻印不可逆"]},
    "history": [{"era": "三百年前", "event": "大封城", "impact": "旧城与外界隔绝"}],
    "characters": [{"name": "主角", "role": "protagonist", "goal": "找回失去的记忆刻印",
                    "inner_need": "被认可", "flaw": "逃避过去", "trait": "记性极好"}],
    "foreshadow_seeds": ["左肩旧伤", "无名令牌"],
}

_PROSE = "他把门推开一条缝，冷风携着雨丝灌进来。墙角的旧钟敲过三下，故事由此展开。"


async def _stub_complete(self, *, task, system, user, max_tokens=None, temperature=None):
    if task == "direction":
        return json.dumps(_STUB_CARDS, ensure_ascii=False)
    if task == "blueprint":
        return json.dumps(_STUB_BLUEPRINT, ensure_ascii=False)
    if task == "consistency":
        return '{"passed": true, "issues": []}'
    if task == "narrative_update":
        return json.dumps({
            "foreshadow_updates": [{"text": "左肩旧伤", "status": "advanced"}],
            "character_updates": [{"name": "主角", "note": "这一拍揭开了身世一角"}],
            "new_foreshadows": ["一枚无名令牌"],
        }, ensure_ascii=False)
    if task == "init":
        return "一个失忆者在雾海旧城寻找身份的故事，基调悬疑，节奏克制。"
    return _PROSE


def _stub_stream(self, *, task, system, user, max_tokens=None, temperature=None):
    async def gen():
        text = await _stub_complete(self, task=task, system=system, user=user,
                                    max_tokens=max_tokens, temperature=temperature)
        step = 12
        for i in range(0, len(text), step):
            yield text[i:i + step]

    return gen()


@pytest.fixture(autouse=True)
def _reset_and_stub(monkeypatch):
    registry.store.reset()
    monkeypatch.setattr(LLMGateway, "complete", _stub_complete)
    monkeypatch.setattr(LLMGateway, "stream", _stub_stream)
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
    assert "world" in bp and "history" in bp and "characters" in bp
    # 前置齐全
    assert bp["world"].get("rules")
    assert bp["world"].get("power_system") is not None
    assert isinstance(bp["characters"], list) and bp["characters"]
    # 初始伏笔从 foreshadow_seeds 长出
    assert isinstance(bp["history"], list)
    assert all(f["text"] in {"左肩旧伤", "无名令牌"} for f in bp["foreshadows"])
    assert all(f["status"] == "planted" for f in bp["foreshadows"])
    # 不再产出预设卷章大纲
    assert "outline" not in bp


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


def test_timeline_grows_with_decisions_world_history_fixed():
    c = _client()
    sid = c.post("/v1/stories", json={"premise": "雾海记忆城"}).json()["story_id"]

    # 开书（开篇非决策）时间线为空
    assert c.get(f"/v1/stories/{sid}/timeline").json()["timeline"] == []
    # 世界历史线是蓝图产物（固定背景），记下其快照
    history = c.get(f"/v1/stories/{sid}/blueprint").json()["history"]
    history_before = list(history)

    # 抽卡 → 时间线追加一条，且带决策上下文
    drawn = c.post(f"/v1/stories/{sid}/decisions/1/gacha").json()
    tl = c.get(f"/v1/stories/{sid}/timeline").json()["timeline"]
    assert len(tl) == 1
    assert tl[0]["decision_no"] == 1
    assert tl[0]["mode"] == "gacha_draw"
    assert tl[0]["card_id"] == drawn["card"]["card_id"]
    assert tl[0]["summary"]

    # 普通 apply → 时间线再追加一条
    created = c.post("/v1/stories", json={"premise": "另一本"}).json()
    sid3 = created["story_id"]
    card_id = created["cards"][0]["card_id"]
    c.post(f"/v1/stories/{sid3}/decisions/1/apply", json={"card_id": card_id})
    tl2 = c.get(f"/v1/stories/{sid3}/timeline").json()["timeline"]
    assert len(tl2) == 1
    assert tl2[0]["label"]  # 从所选卡提炼的 label

    # 抽卡绝不改动世界历史线
    assert c.get(f"/v1/stories/{sid}/blueprint").json()["history"] == history_before


def test_narrative_state_advances_with_decision():
    """决策后：伏笔状态推进、角色增量更新，并回写可视化。"""
    c = _client()
    sid = c.post("/v1/stories", json={"premise": "雾海记忆城"}).json()["story_id"]

    bp0 = c.get(f"/v1/stories/{sid}/blueprint").json()
    assert all(f["status"] == "planted" for f in bp0["foreshadows"])
    assert all(not c0.get("moves") for c0 in bp0["characters"])

    c.post(f"/v1/stories/{sid}/decisions/1/gacha")

    bp1 = c.get(f"/v1/stories/{sid}/blueprint").json()
    statuses = {f["text"]: f["status"] for f in bp1["foreshadows"]}
    assert statuses.get("左肩旧伤") == "advanced"  # 被推进
    protagonist = next(c0 for c0 in bp1["characters"] if c0["name"] == "主角")
    assert protagonist.get("moves")  # 有本段动向
    assert "无名令牌" in statuses  # 已有种子，不重复新增