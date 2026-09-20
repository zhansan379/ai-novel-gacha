"""决策闭环端到端集成测试：stories(async) → cards → gacha/apply → 生成正文。

运行时不再有 mock 降级，因此这里对 LLMGateway.complete/stream 注入测试桩，
用确定性内容驱动整条链路，验证抽卡→正文闭环可跑通（不依赖任何真实模型）。

注意：开书现在是后台异步任务（POST /stories 返回 task_id），必须用「持久 portal」
的 TestClient（with 块）让后台任务在同一事件循环存活，再轮询 tasks 拿到 done 结果。
"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.llm import LLMGateway
from app.llm.errors import ModelError
from app.services import registry

_STUB_CARDS = [
    {"card_id": "t-a", "title": "夜雨敲门", "label": "EVENT", "rarity": "R", "weight": 40,
     "content": "雨夜有人敲门，指名要找主角。",
     "cause": "主角在当铺亮了那件旧物，被眼线盯上并报信到此",
     "aftermath": "来客态度成谜，主角与其对峙，得知自己被悬赏追查",
     "suspense": "来客掏出的画像像是主角年少时的自己"},
    {"card_id": "t-b", "title": "落魄画师", "label": "MEETING", "rarity": "SR", "weight": 25,
     "content": "画师认出了主角身上的一件旧物。",
     "cause": "画师曾在旧王宫给贵人画像，认得过这件旧物",
     "aftermath": "画师欲言又止，暗示旧物主人身份不简单，主角追问他愿谈的条件",
     "suspense": "画师说旧物尚有一件在别人手里",
     "risk_balance": {"tension": 6, "suggested_turn": "画师揭晓关于主角过去的线索"}},
    {"card_id": "t-c", "title": "无名密信", "label": "FORESHADOW", "rarity": "N", "weight": 60,
     "content": "一封没有落款的信，笔迹却异常熟悉。",
     "cause": "信是趁主角出门时塞进门缝的，无人看见送信人",
     "aftermath": "主角读信后脸色骤变，开始怀疑身边的人",
     "suspense": "信上提到的那日正是主角失忆的那日"},
]

# —— 蓝图层拆六路分段构建，各自返回自己的切片 ——
_STUB_SKELETON = {
    "era": "旧纪", "world_tone": "悬疑克制", "geography_brief": "临海多雾的旧城",
    "power_system_brief": "记忆刻印", "factions": ["守刻人"],
    "protagonist_anchor": "一个在雾海旧城寻回身份的失忆者",
}
_STUB_WORLD = {"rules": ["魔法受七日蚀月周期影响"], "geography": "雾海旧城",
               "power_system": "记忆刻印", "constraints": ["刻印不可逆"]}
_STUB_HISTORY = [{"era": "三百年前", "event": "大封城", "impact": "旧城与外界隔绝"}]
_STUB_CHARACTERS = [{"name": "主角", "role": "protagonist", "goal": "找回失去的记忆刻印",
                     "inner_need": "被认可", "flaw": "逃避过去", "trait": "记性极好"}]
_STUB_FORESHADOWS = ["左肩旧伤", "无名令牌"]
_STUB_RELATIONSHIPS = []  # 开书初始不给关系边（随剧情推进才长出）

_PROSE = "他把门推开一条缝，冷风携着雨丝灌进来。墙角的旧钟敲过三下，故事由此展开。"


async def _stub_complete(self, *, task, system, user, max_tokens=None, temperature=None):
    if task == "direction":
        return json.dumps(_STUB_CARDS, ensure_ascii=False)
    if task == "blueprint":
        return json.dumps({"world": _STUB_WORLD, "history": _STUB_HISTORY,
                           "characters": _STUB_CHARACTERS,
                           "foreshadow_seeds": _STUB_FORESHADOWS}, ensure_ascii=False)
    if task == "blueprint_skeleton":
        return json.dumps(_STUB_SKELETON, ensure_ascii=False)
    if task == "blueprint_world":
        return json.dumps(_STUB_WORLD, ensure_ascii=False)
    if task == "blueprint_history":
        return json.dumps(_STUB_HISTORY, ensure_ascii=False)
    if task == "blueprint_characters":
        return json.dumps(_STUB_CHARACTERS, ensure_ascii=False)
    if task == "blueprint_foreshadows":
        return json.dumps(_STUB_FORESHADOWS, ensure_ascii=False)
    if task == "blueprint_relationships":
        return json.dumps(_STUB_RELATIONSHIPS, ensure_ascii=False)
    if task == "consistency":
        return '{"passed": true, "issues": []}'
    if task == "narrative_update":
        return json.dumps({
            "foreshadow_updates": [{"text": "左肩旧伤", "status": "advanced"}],
            "character_updates": [{"name": "主角", "note": "这一拍揭开了身世一角"}],
            "relation_updates": [{"a": "主角", "b": "守刻人", "label": "隶属", "note": "得知身世与守刻人的纠葛"}],
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


@pytest.fixture
def client():
    # 持久 portal：让异步开书任务在请求间存活，轮询到 done 而非随单次请求被回收
    with TestClient(app) as c:
        yield c


def _create(client: TestClient, premise: str) -> dict:
    """提交开书任务 → 轮询状态直到 done，返回 StoryCreated 同形态的 result。"""
    r = client.post("/v1/stories", json={"premise": premise})
    assert r.status_code == 202, r.text
    task_id = r.json()["task_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        st = client.get(f"/v1/stories/tasks/{task_id}")
        assert st.status_code == 200, st.text
        body = st.json()
        if body["status"] == "done":
            result = body["result"]
            assert result and result["story_id"]
            return result
        if body["status"] == "error":
            raise AssertionError(f"开书任务失败: {body['error']}")
        time.sleep(0.05)
    raise AssertionError(f"开书任务超时，状态: {st.json()['status']}")


def test_create_story_returns_opening_and_first_decision(client):
    body = _create(client, "一个失忆的杀手想找回身份")
    assert body["story_id"]
    assert len(body["opening"]) > 10
    assert body["decision_no"] == 1
    assert 3 <= len(body["cards"]) <= 5


def test_full_blind_gacha_loop(client):
    created = _create(client, "暴雨中的空城")
    sid, no = created["story_id"], created["decision_no"]

    got = client.get(f"/v1/stories/{sid}/decisions/{no}/cards")
    assert got.status_code == 200
    cards = got.json()["cards"]
    assert 3 <= len(cards) <= 5

    drawn = client.post(f"/v1/stories/{sid}/decisions/{no}/gacha").json()
    assert drawn["mode"] == "gacha_draw"
    assert drawn["card"]["card_id"] in {c_["card_id"] for c_ in cards}
    assert len(drawn["passage"]) > 10
    assert drawn["next_decision_no"] == 2

    # 已锁定 → 重复 gacha 返回 409
    again = client.post(f"/v1/stories/{sid}/decisions/{no}/gacha")
    assert again.status_code == 409


def test_pick_and_free_apply(client):
    created = _create(client, "末日后的图书馆")
    sid, no = created["story_id"], created["decision_no"]
    card_id = created["cards"][0]["card_id"]

    picked = client.post(f"/v1/stories/{sid}/decisions/{no}/apply", json={"card_id": card_id}).json()
    assert picked["mode"] == "gacha_pick"
    assert len(picked["passage"]) > 10

    # 下一决策自由输入
    nxt = picked["next_decision_no"]
    free = client.post(f"/v1/stories/{sid}/decisions/{nxt}/apply",
                       json={"custom_instruction": "让主角在旧码头发现藏宝图"}).json()
    assert free["mode"] == "free"
    assert len(free["passage"]) > 10


def test_apply_unknown_card_422(client):
    sid = _create(client, "x")["story_id"]
    r = client.post(f"/v1/stories/{sid}/decisions/1/apply", json={"card_id": "nope"})
    assert r.status_code == 422


def test_apply_missing_both_rejected(client):
    sid = _create(client, "x")["story_id"]
    r = client.post(f"/v1/stories/{sid}/decisions/1/apply", json={})
    assert r.status_code == 422


def test_unknown_story_404(client):
    r = client.get("/v1/stories/nope")
    assert r.status_code == 404


def test_blueprint_built_and_persisted(client):
    sid = _create(client, "雾海中的记忆之城")["story_id"]

    bp = client.get(f"/v1/stories/{sid}/blueprint").json()
    assert "world" in bp and "history" in bp and "characters" in bp
    # 前置齐全
    assert bp["world"].get("rules")
    assert bp["world"].get("power_system") is not None
    assert isinstance(bp["characters"], list) and bp["characters"]
    # 初始伏笔从 foreshadow_seeds 长出
    assert isinstance(bp["history"], list)
    assert all(f["text"] in {"左肩旧伤", "无名令牌"} for f in bp["foreshadows"])
    assert all(f["status"] == "planted" for f in bp["foreshadows"])
    # 骨架势力并进 world.factions
    assert bp["world"].get("factions") == ["守刻人"]
    # 初始蓝图未产关系边 → 关系账本为空（随剧情推进才长出）
    assert bp["relations"] == []
    # 不再产出预设卷章大纲
    assert "outline" not in bp


def test_quality_fields_in_draw_and_relint_endpoint(client):
    sid = _create(client, "质检测试")["story_id"]
    drawn = client.post(f"/v1/stories/{sid}/decisions/1/gacha").json()
    assert "lint" in drawn and isinstance(drawn["lint"], list)
    assert "consistency" in drawn and drawn["consistency"]["passed"] is True

    rel = client.post(f"/v1/stories/{sid}/passages/1/lint")
    assert rel.status_code == 200
    assert "lint" in rel.json() and "consistency" in rel.json()


def test_stream_decision_sse(client):
    sid = _create(client, "流式测试")["story_id"]
    r = client.post(f"/v1/stories/{sid}/decisions/1/stream", json={"draw": True})
    assert r.status_code == 200
    body = r.text
    assert "event: passage_start" in body
    assert "event: delta" in body
    assert "event: passage_end" in body
    assert '"next_decision_no": 2' in body
    assert '"lint"' in body


def test_stream_requires_one_action(client):
    sid = _create(client, "x")["story_id"]
    # draw + card_id 同时存在 → 422
    r = client.post(f"/v1/stories/{sid}/decisions/1/stream",
                    json={"draw": True, "custom_instruction": "x"})
    assert r.status_code == 422


def test_timeline_grows_with_decisions_world_history_fixed(client):
    sid = _create(client, "雾海记忆城")["story_id"]

    # 开书（开篇非决策）时间线为空
    assert client.get(f"/v1/stories/{sid}/timeline").json()["timeline"] == []
    # 世界历史线是蓝图产物（固定背景），记下其快照
    history = client.get(f"/v1/stories/{sid}/blueprint").json()["history"]
    history_before = list(history)

    # 抽卡 → 时间线追加一条，且带决策上下文
    drawn = client.post(f"/v1/stories/{sid}/decisions/1/gacha").json()
    tl = client.get(f"/v1/stories/{sid}/timeline").json()["timeline"]
    assert len(tl) == 1
    assert tl[0]["decision_no"] == 1
    assert tl[0]["mode"] == "gacha_draw"
    assert tl[0]["card_id"] == drawn["card"]["card_id"]
    assert tl[0]["summary"]

    # 普通 apply → 时间线再追加一条
    created2 = _create(client, "另一本")
    sid3 = created2["story_id"]
    card_id = created2["cards"][0]["card_id"]
    client.post(f"/v1/stories/{sid3}/decisions/1/apply", json={"card_id": card_id})
    tl2 = client.get(f"/v1/stories/{sid3}/timeline").json()["timeline"]
    assert len(tl2) == 1
    assert tl2[0]["label"]  # 从所选卡提炼的 label

    # 抽卡绝不改动世界历史线
    assert client.get(f"/v1/stories/{sid}/blueprint").json()["history"] == history_before


def test_narrative_state_advances_with_decision(client):
    """决策后：伏笔状态推进、角色增量更新，并回写可视化。"""
    sid = _create(client, "雾海记忆城")["story_id"]

    bp0 = client.get(f"/v1/stories/{sid}/blueprint").json()
    assert all(f["status"] == "planted" for f in bp0["foreshadows"])
    assert all(not c0.get("moves") for c0 in bp0["characters"])

    client.post(f"/v1/stories/{sid}/decisions/1/gacha")

    bp1 = client.get(f"/v1/stories/{sid}/blueprint").json()
    statuses = {f["text"]: f["status"] for f in bp1["foreshadows"]}
    assert statuses.get("左肩旧伤") == "advanced"  # 被推进
    protagonist = next(c0 for c0 in bp1["characters"] if c0["name"] == "主角")
    assert protagonist.get("moves")  # 有本段动向
    assert "无名令牌" in statuses  # 已有种子，不重复新增
    # 关系账本随推进长出：主角-守刻人 隶属边出现
    assert any(
        r["a"] == "主角" and r["b"] == "守刻人" and r["label"] == "隶属"
        for r in bp1["relations"]
    )


def test_undo_last_step_restores_state(client):
    sid = _create(client, "雾海记忆城")["story_id"]
    assert all(f["status"] == "planted" for f in client.get(f"/v1/stories/{sid}/blueprint").json()["foreshadows"])

    client.post(f"/v1/stories/{sid}/decisions/1/gacha")
    bp1 = client.get(f"/v1/stories/{sid}/blueprint").json()
    assert any(f["status"] == "advanced" for f in bp1["foreshadows"])

    r = client.post(f"/v1/stories/{sid}/undo")
    assert r.status_code == 200
    assert r.json()["next_decision_no"] == 1
    assert len(client.get(f"/v1/stories/{sid}").json()["passages"]) == 1  # 只剩开篇

    # 角色与伏笔回退到本步推进前
    bp2 = client.get(f"/v1/stories/{sid}/blueprint").json()
    assert all(f["status"] == "planted" for f in bp2["foreshadows"])
    assert all(not c0.get("moves") for c0 in bp2["characters"])
    # 关系账本同样回滚：推进时新增的隶属边被撤销
    assert bp2["relations"] == []

    # 解锁后可重新选择
    assert client.post(f"/v1/stories/{sid}/decisions/1/gacha").status_code == 200


def test_undo_with_nothing_returns_409(client):
    sid = _create(client, "x")["story_id"]
    r = client.post(f"/v1/stories/{sid}/undo")
    assert r.status_code == 409


def test_stream_mid_generation_failure_is_graceful_and_rolls_back(monkeypatch, client):
    sid = _create(client, "雾海记忆城")["story_id"]

    # 让"正文流"(SSE 的 draft 段)中途抛错，验证流式生成失败被优雅捕获并回滚。
    # （卡池生成已移出正文流，因此用正文流本身作为失败源，保证"中途失败→优雅收尾→可重试"）
    def fail_stream(self, *, task, system, user, max_tokens=None, temperature=None):
        async def broken():
            raise ModelError("正文生成中途失败")
            yield "".encode()  # noqa: PIE790 永不可达；保证这是个 async generator
        return broken()

    monkeypatch.setattr(LLMGateway, "stream", fail_stream)
    r = client.post(f"/v1/stories/{sid}/decisions/1/stream", json={"draw": True})
    assert r.status_code == 200
    # 已是 SSE 流，不应崩溃；且发出 passage_error 而非无声截断
    assert "event: passage_error" in r.text
    # 服务端已回滚：该步正文未持久化，正文仍只剩开篇
    assert len(client.get(f"/v1/stories/{sid}").json()["passages"]) == 1

    # 决策未被锁死：恢复好桩后重试不再 409
    monkeypatch.setattr(LLMGateway, "complete", _stub_complete)
    monkeypatch.setattr(LLMGateway, "stream", _stub_stream)
    assert client.post(f"/v1/stories/{sid}/decisions/1/gacha").status_code == 200