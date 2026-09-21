"""出场人物建档：register_appearances / drop_formalized_appearances / extract_names / 持久化往返。"""
import json

import pytest

from app.schemas import DirectionKind, DirectionSpec
from app.services import registry
from app.services.narrative import (NarrativeUpdater, register_appearances,
                                    drop_formalized_appearances)
from app.services.store import Story
from app.storage.sqlite import SQLiteStore


def _stub_completer(raw: str):
    class _Stub:
        async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
            return raw
    return _Stub()


def test_register_below_threshold_stays_in_appearances():
    apps, chars, reg, prom = register_appearances(
        [], [{"name": "林浩", "role": "protagonist"}], ["李健国"],
        passage_no=1, threshold=2)
    assert prom == []
    assert reg == ["李健国"]
    assert [a["name"] for a in apps] == ["李健国"]
    assert apps[0]["count"] == 1 and apps[0]["first_no"] == 1
    assert [c["name"] for c in chars] == ["林浩"]  # 正式角色不受影响


def test_register_promotes_at_threshold_and_drops_from_appearances():
    apps, chars, reg, prom = register_appearances(
        [], [{"name": "林浩", "role": "protagonist"}], ["李健国"],
        passage_no=1, threshold=2)
    apps, chars, reg2, prom2 = register_appearances(
        apps, chars, ["李健国"], passage_no=2, threshold=2)
    assert prom2 == ["李健国"]
    assert reg2 == []
    assert [a["name"] for a in apps] == []                     # 已升格 → 出场账本清空
    promoted = next(c for c in chars if c["name"] == "李健国")  # 升格为正式角色
    assert promoted["role"] == "supporter"


def test_register_ignores_known_characters():
    apps, chars, reg, prom = register_appearances(
        [], [{"name": "林浩", "role": "protagonist"}], ["林浩", "李健国"],
        passage_no=1, threshold=2)
    assert reg == ["李健国"]        # 林浩已是角色，不重复建档
    assert [a["name"] for a in apps] == ["李健国"]


def test_drop_formalized_appearances_removes_promoted_names():
    apps = [{"name": "李健国", "count": 1, "first_no": 1},
            {"name": "王五", "count": 1, "first_no": 2}]
    chars = [{"name": "林浩", "role": "protagonist"}, {"name": "李健国", "role": "supporter"}]
    out = drop_formalized_appearances(apps, chars)
    assert [a["name"] for a in out] == ["王五"]


@pytest.mark.anyio
async def test_extract_names_filters_known_and_dedupes():
    gw = _stub_completer('["李健国", "李健国", "林浩", ""]')
    names = await NarrativeUpdater(gw).extract_names(passage="正文", known=["林浩"])
    assert names == ["李健国"]  # 已知角色剔除、重复去重、空串丢弃


@pytest.mark.anyio
async def test_extract_names_raises_on_non_array():
    up = NarrativeUpdater(_stub_completer("不是数组"))
    with pytest.raises(Exception):
        await up.extract_names(passage="正文", known=[])


def _story_with_appearances() -> Story:
    story = Story(id="s-app", premise="p", synopsis="s")
    story.appearances.append({"name": "李健国", "count": 1, "first_no": 1})
    story.appearances.append({"name": "王五", "count": 2, "first_no": 2})
    return story


def test_appearances_persist_roundtrip(tmp_path):
    path = str(tmp_path / "app.db")
    store = SQLiteStore(path)
    store.save(_story_with_appearances())
    store.close()

    reloaded = SQLiteStore(path).get("s-app")
    assert [a["name"] for a in reloaded.appearances] == ["李健国", "王五"]
    assert reloaded.appearances[1]["count"] == 2


@pytest.mark.anyio
async def test_advance_state_records_appearance_and_retries_narrative_update():
    """Option 3: narrative.update 首调失败 → 重试成功；出场人物仍建档；升格后清出账本。"""
    calls = {"n": 0}

    class _Gate:
        async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
            if task == "appearance":
                return '["李健国"]'
            if task == "narrative_update":
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("transient")
                return json.dumps({
                    "character_updates": [{"name": "李健国", "note": "本拍揭晓身世"}],
                    "foreshadow_updates": [],
                    "new_foreshadows": [],
                    "relation_updates": [],
                }, ensure_ascii=False)
            raise AssertionError(f"unexpected task: {task}")

    svc = registry.story_service
    svc._narrative = NarrativeUpdater(_Gate())

    story = Story(id="s-retry", premise="p", synopsis="s")
    story.characters = [{"name": "林浩", "role": "protagonist"}]
    spec = DirectionSpec(kind=DirectionKind.EVENT, summary="推进")

    info = await svc._advance_state(story, spec, "正文里李健国登场了", passage_no=1)

    assert calls["n"] == 2                          # 失败一次后重试成功
    assert info["update_failed"] is False
    assert "李健国" in [c["name"] for c in story.characters]   # 被叙事更新补录为正式角色
    assert all(a["name"] != "李健国" for a in story.appearances)  # 升格后从出场账本清掉
    assert "李健国" in info["appearances"]