from app.services.facts import build_facts, init_foreshadows
from app.services.store import Story


def test_init_foreshadows_dedupes_and_filters_empty():
    outline = [
        {"type": "act", "no": 1, "foreshadow": "左肩旧伤"},
        {"type": "chapter", "no": 2, "foreshadow": "一枚无名令牌"},
        {"type": "chapter", "no": 3, "foreshadow": ""},
        {"type": "chapter", "no": 4, "foreshadow": "左肩旧伤"},  # 重复
    ]
    fs = init_foreshadows(outline)
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
        outline=[{"type": "chapter", "no": 1, "foreshadow": "无名令牌"}],
    )
    story.foreshadows = init_foreshadows(story.outline)
    facts = build_facts(story)
    joined = "\n".join(facts)
    assert "阿刻" in joined
    assert "刻印不可逆" in joined
    assert "无名令牌" in joined
    # inset rules 与伏笔都在


def test_build_facts_empty_story():
    assert build_facts(Story(id="s", premise="p", synopsis="s")) == []