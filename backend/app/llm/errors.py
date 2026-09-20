"""应用公共异常。"""
from __future__ import annotations


class LLMError(Exception):
    """LLM 调用失败基类。"""


class ModelError(LLMError):
    """上游模型返回错误/网络失败。"""


class QuotaError(LLMError):
    """配额/限流超限。"""