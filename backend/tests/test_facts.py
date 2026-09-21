from app.services.facts import build_facts, build_narrative_context, init_foreshadows
from app.services.store import Story, normalize_factions


def test_normalize_factions_mixed_and_dirty():
    # 新版对象 + 旧版字符串 + 缺 name 的脏项混用：统一归一到 [{name, description}]
    mixed = [
        {"name": "守刻人", "description": "守卫旧城记忆的秘教"},
        "旧字",
        {"name": ""},
        {"name": "无名帮", "description": "雾海走私团伙"},
        None,
    ]
    assert normalize_factions(mixed) == [
        {"name": "守刻人", "description": "守卫旧城记忆的秘教"},
        {"name": "旧字", "description": ""},
        {"name": "无名帮", "description": "雾海走私团伙"},
    ]
    assert normalize_factions(None) == []
    assert normalize_factions([]) == []


def test_factions_in_context_and_facts_legacy_string_and_object():
    story = Story(id="s", premise="p", synopsis="s", characters=[
        {"name": "主角", "role": "protagonist", "goal": "找回记忆"},
    ])
    story.world = {"rules": ["刻印不可逆"], "factions": [
        {"name": "守刻人", "description": "秘教"},
        "旧字",  # 存量字符串仍兼容
    ]}
    ctx = build_narrative_context(story)
    assert "势力「守刻人」：秘教" in ctx
    assert "势力「旧字」" in ctx
    facts = "\n".join(build_facts(story))
    assert "势力：守刻人——秘教" in facts
    assert "势力：旧字" in facts


def test_init_foreshadows_dedupes_and_filters_empty():
    seeds = ["左肩旧伤", "一枚无名令牌", "", "左肩旧伤"]  # 空与重复均剔除
    fs = init_foreshadows(seeds)
    assert [f["text"] for f in fs] == ["左肩旧伤", "一枚无名令牌"]
    assert all(f["status"] == "planted" for f in fs)


def test_build_facts_from_blueprint():
    story = Story(
        id="s", premise="p", synopsis="s",
        characters=[
            {"name": "阿刻", "role": "protagonist", "goal": "找回记忆", "inner_need": "被记起", "flaw": "逃避"},
            {"name": "刻影", "role": "supporter", "goal": "真相", "inner_need": "", "flaw": ""},
        ],
        world={"rules": ["刻印不可逆"], "constraints": ["每次刻印消耗记忆"]},
    )
    story.foreshadows = init_foreshadows(["无名令牌"])
    facts = build_facts(story)
    joined = "\n".join(facts)
    assert "阿刻" in joined
    assert "刻印不可逆" in joined
    assert "无名令牌" in joined
    # inset rules 与伏笔都在


def test_build_facts_empty_story():
    assert build_facts(Story(id="s", premise="p", synopsis="s")) == []


def _story_with_timeline(*, n_chars=2, n_fs=2, n_rels=0, tl=None):
    story = Story(id="s", premise="p", synopsis="s")
    story.characters = [
        {"name": f"角色{i}", "role": "protagonist" if i == 0 else "supporter",
         "goal": f"目标{i}", "trait": f"特征{i}"}
        for i in range(n_chars)
    ]
    story.foreshadows = [{"id": f"fs{i}", "text": f"伏笔文本{i}",
                          "status": "planted" if i % 2 == 0 else "advanced"} for i in range(n_fs)]
    story.world = {"rules": ["世界规则A"], "constraints": ["世界限制B"]}
    story.relations = [
        {"a": f"角色{a}", "b": f"角色{b}", "label": "认识", "note": "n"} for a, b in _rel_pairs(n_rels)
    ]
    if tl is not None:
        story.timeline = tl
    return story


def _rel_pairs(n):
    # n 对边：关系0 连到 角色0/角色1，关系1 连到 角色1/角色2 ... 与角色计数解耦
    out = []
    for i in range(n):
        out.append((f"角色{i % 4}", f"角色{(i + 1) % 4}"))
    return out


class TestRecentMemory:
    def test_timeline_produces_recent_plot_block(self):
        tl = [{"no": 1, "mode": "gacha", "title": "雨夜敲门", "summary": "主角听到敲门声"},
              {"no": 2, "mode": "free", "title": "码头", "summary": "主角在码头遇见画师"},
              {"no": 3, "mode": "gacha", "title": "旧物", "summary": "画师认出那件旧物"}]
        ctx = build_narrative_context(_story_with_timeline(tl=tl))
        assert "【近期剧情】" in ctx
        assert "雨夜敲门" in ctx and "码头" in ctx and "旧物" in ctx

    def test_recent_block_capped_at_max_recent(self):
        tl = [{"no": i, "mode": "m", "title": f"拍{i}", "summary": f"剧情{i}"} for i in range(1, 9)]
        ctx = build_narrative_context(_story_with_timeline(tl=tl))
        plot_lines = [l for l in ctx.splitlines() if l.startswith("- #")]
        assert len(plot_lines) <= 4  # 只保留最后 max_recent(4) 拍
        assert "拍1" not in ctx and "拍2" not in ctx and "拍3" not in ctx and "拍4" not in ctx
        assert "拍8" in ctx and "拍7" in ctx and "拍6" in ctx and "拍5" in ctx

    def test_no_timeline_has_no_plot_block_and_all_preserved(self):
        ctx = build_narrative_context(_story_with_timeline(n_chars=3, n_fs=3))
        assert "【近期剧情】" not in ctx
        assert "世界规则A" in ctx and "世界限制B" in ctx
        for i in range(3):
            assert f"角色{i}" in ctx
        for i in range(3):
            assert f"伏笔文本{i}" in ctx


class TestRelevanceTrimming:
    def test_many_characters_capped_with_protagonist_kept(self):
        story = _story_with_timeline(n_chars=9)
        ctx = build_narrative_context(story)
        chars = [l for l in ctx.splitlines() if l.startswith("- 角色「")]
        assert len(chars) <= 6
        assert any("角色0" in c and "主角" in c for c in chars)  # 主角恒在

    def test_foreshadows_capped_prefer_active(self):
        story = _story_with_timeline(n_fs=12)
        story.foreshadows[0]["status"] = "paid_off"  # 让第一条已兑现
        ctx = build_narrative_context(story)
        fs = [l for l in ctx.splitlines() if l.startswith("- 伏笔(")]
        assert len(fs) <= 8
        # 已兑现那条在不超限内尽量被挤出
        assert "伏笔(已兑现)" not in ctx

    def test_relevance_keeps_beat_related_character(self):
        # 相关键 = 最近一拍摘要；含"李家"，则"李家家主"这类联动该被保留
        tl = [{"no": 1, "mode": "m", "title": "x", "summary": "主角去找李家家主谈联手"}]
        story = _story_with_timeline(n_chars=9, tl=tl)
        story.characters[1] = {"name": "李家家主", "role": "supporter", "goal": "重振李家", "trait": "沉"}
        ctx = build_narrative_context(story)
        assert "李家家主" in ctx  # 相关键命中 → 即使角色多也被保留

    def test_too_many_relations_capped(self):
        story = _story_with_timeline(n_chars=3, n_rels=12)
        ctx = build_narrative_context(story)
        rels = [l for l in ctx.splitlines() if l.startswith("- 关系：")]
        assert len(rels) <= 10


class TestFactsStaysComplete:
    def test_build_facts_always_full_regardless_of_context_trimming(self):
        story = _story_with_timeline(n_chars=12, n_fs=12, n_rels=12)
        facts = "\n".join(build_facts(story))
        for i in range(12):
            assert f"角色{i}" in facts
            assert f"伏笔文本{i}" in facts
        assert "世界规则A" in facts and "世界限制B" in facts