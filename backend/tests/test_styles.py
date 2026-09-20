from app.services.styles import STYLE_PROFILES, get_style, list_styles, match_style_id, style_choice_text


def test_at_least_five_styles():
    assert len(STYLE_PROFILES) >= 5


def test_style_fields_complete():
    for s in STYLE_PROFILES.values():
        assert s.id and s.name and s.description
        assert 0.0 <= s.temperature <= 1.5
        assert s.system_prompt


def test_get_style_default_and_unknown_fallback():
    assert get_style(None).id == "restrained"
    assert get_style("not-a-style").id == "restrained"
    assert get_style("wuxia").id == "wuxia"


def test_list_styles_shape():
    items = list_styles()
    assert isinstance(items, list) and len(items) == len(STYLE_PROFILES)
    for it in items:
        assert {"id", "name", "description", "temperature", "forbidden"} <= set(it)


def test_match_style_id():
    # 直接命中
    assert match_style_id("wuxia") == "wuxia"
    # 包裹文字/大小写宽容
    assert match_style_id("推荐：urban。") == "urban"
    assert match_style_id("XIANXIA") == "xianxia"
    # 无效/空 → None
    assert match_style_id("") is None
    assert match_style_id(None) is None
    assert match_style_id("搞不懂") is None


def test_style_choice_text_lists_all():
    text = style_choice_text()
    for pid in STYLE_PROFILES:
        assert pid in text