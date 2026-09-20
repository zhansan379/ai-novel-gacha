"""openai_compat：Base URL 归一化单测（避免重复拼接 /chat/completions）。"""
from app.llm.openai_compat import completions_url


def test_appends_for_prefix_url():
    assert completions_url("https://api.xxx.com/v1") == "https://api.xxx.com/v1/chat/completions"


def test_does_not_double_append_full_endpoint():
    assert completions_url("https://api.xxx.com/v1/chat/completions") == \
        "https://api.xxx.com/v1/chat/completions"


def test_trailing_slash_normalized():
    assert completions_url("https://api.xxx.com/v1/") == "https://api.xxx.com/v1/chat/completions"