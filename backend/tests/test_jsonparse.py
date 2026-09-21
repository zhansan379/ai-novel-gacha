import pytest

from app.services.jsonparse import loads_coerce


def test_plain_object():
    assert loads_coerce('{"a": 1}') == {"a": 1}


def test_fenced_object():
    assert loads_coerce('```json\n{"a": 1}\n```') == {"a": 1}


def test_intro_text_before_json():
    assert loads_coerce('好的，伏笔如下：\n{"seeds": ["x"]}') == {"seeds": ["x"]}


def test_raw_newline_inside_string_is_repaired():
    raw = '{"world": {"geography": "旧城位于洼地，\n街道曲折。", "rules": ["a"]}}'
    assert loads_coerce(raw) == {
        "world": {"geography": "旧城位于洼地，\n街道曲折。", "rules": ["a"]}
    }


def test_trailing_comma_is_repaired():
    assert loads_coerce('{"rules": ["a", "b",]}') == {"rules": ["a", "b"]}
    assert loads_coerce('[1, 2, 3,]') == [1, 2, 3]


def test_outermost_span_not_inner_array():
    """顶层对象内部带裸换行时，不能把内层数组当成整个结果返回（silent 损坏回归）。"""
    raw = '```json\n{"world": {"geography": "旧城，\n多雨。", "rules": ["a", "b"]}}\n```'
    assert loads_coerce(raw) == {
        "world": {"geography": "旧城，\n多雨。", "rules": ["a", "b"]}
    }


def test_plain_array():
    assert loads_coerce('[{"era": "一"}, {"era": "二"}]') == [
        {"era": "一"}, {"era": "二"}
    ]


def test_unparseable_raises():
    with pytest.raises(Exception):
        loads_coerce('这不是 JSON')