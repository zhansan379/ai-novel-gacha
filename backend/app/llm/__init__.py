"""LLM 接入层：提供统一 complete() 抽象，真实(OpenAI 兼容) + 本地 mock 双实现。

- 无 API Key / 服务商不可用时自动回退到本地 mock，保证 demo/测试无需密钥即可跑通闭环。
- 具体任务与温度路由见 routing.py。
"""
from __future__ import annotations

from app.llm.errors import LLMError, ModelError, QuotaError
from app.llm.gateway import LLMGateway

__all__ = ["LLMGateway", "LLMError", "ModelError", "QuotaError"]