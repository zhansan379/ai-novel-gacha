"""LLM 接入层：提供统一 complete() 抽象，真实实现走 OpenAI 兼容协议。

- 未配置任何模型（无 Key）时，complete/stream 抛出 ModelError 明确提示，不再静默降级 mock。
- 具体任务与温度/长度路由见 routing.py。
"""
from __future__ import annotations

from app.llm.errors import LLMError, ModelError, QuotaError
from app.llm.gateway import LLMGateway

__all__ = ["LLMGateway", "LLMError", "ModelError", "QuotaError"]