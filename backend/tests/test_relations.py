"""关系账本：增量合并（_apply_relations）+ 注入 build_facts。"""
from app.services.facts import build_facts, build_narrative_context
from app.services.narrative import _apply_relations
from app.services.store import Story


def test_apply_relations_dedups_direction_agnostic():
    rel = [{"a": "沈惊鸿", "b": "陆沉舟", "label": "师徒", "note": ""}]
    # B-A 方向新增同一对实体 → 不应产生第二条边，只更新 label
    out = _apply_relations(rel, [{"a": "陆沉舟", "b": "沈惊鸿", "label": "决裂", "note": "反目"}])
    assert len(out) == 1
    assert out[0] == {"a": "沈惊鸿", "b": "陆沉舟", "label": "决裂", "note": "反目"}


def test_apply_relations_adds_new_edge():
    out = _apply_relations([], [{"a": "阿刻", "b": "无名令牌会", "label": "隶属", "note": "暗卫"}])
    assert out == [{"a": "无名令牌会", "b": "阿刻", "label": "隶属", "note": "暗卫"}]


def test_apply_relations_severs_removes_edge():
    rel = [{"a": "甲", "b": "乙", "label": "同盟", "note": ""},
           {"a": "甲", "b": "丙", "label": "仇敌", "note": ""}]
    out = _apply_relations(rel, [{"a": "甲", "b": "乙", "status": "severed"}])
    assert len(out) == 1
    assert out[0]["b"] == "丙"


def test_apply_relations_ignores_invalid():
    rel = [{"a": "甲", "b": "乙", "label": "同盟", "note": ""}]
    # 空端点 / 自环 / 无 a 无 b 都应被忽略且不产生新边
    out = _apply_relations(rel, [{"a": "", "b": "丙", "label": "x"}, {"a": "甲", "b": "甲", "label": "y"}])
    assert len(out) == 1


def test_build_facts_includes_relations():
    story = Story(
        id="s", premise="p", synopsis="s",
        relations=[{"a": "沈惊鸿", "b": "陆沉舟", "label": "师徒", "note": "曾被逐出师门"}],
        characters=[{"name": "沈惊鸿", "role": "protagonist"}],
    )
    joined = "\n".join(build_facts(story))
    assert "沈惊鸿 师徒 陆沉舟" in joined
    assert "曾被逐出师门" in joined


def test_build_narrative_context_includes_relations():
    story = Story(
        id="s", premise="p", synopsis="s",
        relations=[{"a": "阿刻", "b": "刻影", "label": "宿敌", "note": ""}],
    )
    ctx = build_narrative_context(story)
    assert "阿刻 宿敌 刻影" in ctx


def test_build_facts_empty_relations_ok():
    story = Story(id="s", premise="p", synopsis="s", characters=[{"name": "孤身", "role": "protagonist"}])
    assert "关系：孤身" not in "\n".join(build_facts(story))