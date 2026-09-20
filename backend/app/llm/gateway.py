"""LLM Gateway：按提供商/密钥调度到 OpenAI 兼容实现；无密钥自动回退本地 mock。

消费方只调用 `gateway.complete(task, system, user)`，不感知具体实现。
"""
from __future__ import annotations

from app.config import Settings
from app.llm.routing import Route, route_for

from .mock import MockLLM
from .openai_compat import OpenAICompatLLM


class LLMGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _provider_route(self, task: str) -> Route:
        # direction 类任务用默认提供商，正文类默认；此处统一走路由表
        return route_for(task)

    async def complete(self, *, task: str, system: str, user: str, max_tokens: int | None = None,
                       temperature: float | None = None) -> str:
        provider = self.settings.default_provider
        api_key = self.settings.api_keys.get(provider)
        route = self._provider_route(task)
        if temperature is not None:  # 文风可覆盖默认温度
            route = Route(temperature=temperature, max_tokens=route.max_tokens)

        # 无 key → 本地 mock 降级（demo/测试可跑通闭环）
        if not api_key:
            mock = MockLLM(provider=provider)
            return await mock.complete(task=task, system=system, user=user,
                                       max_tokens=max_tokens or route.max_tokens,
                                       temperature=route.temperature)

        base_url = self.settings.base_urls.get(provider, self.settings.openai_compat_base_url)
        llm = OpenAICompatLLM(
            base_url=base_url,
            api_key=api_key,
            model=self.settings.default_model,
            route=route,
            timeout=self.settings.llm_timeout,
        )
        return await llm.complete(system=system, user=user, max_tokens=max_tokens)

    def mode(self) -> str:
        provider = self.settings.default_provider
        return "openai-compat" if self.settings.api_keys.get(provider) else "mock"