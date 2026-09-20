"""LLM Gateway：按提供商/密钥调度到 OpenAI 兼容实现；无有效配置自动回退本地 mock。

配置优先级：Keychain 运行时配置（前端可设）> 环境变量/.env（settings）。
消费方只调用 `gateway.complete(task, system, user)` / `gateway.stream(...)`，不感知具体实现。
"""
from __future__ import annotations

from app.config import Settings
from app.llm.routing import Route, route_for
from app.services.keychain import Keychain

from .mock import MockLLM
from .openai_compat import OpenAICompatLLM


class LLMGateway:
    def __init__(self, settings: Settings, keychain: Keychain | None = None) -> None:
        self.settings = settings
        self._keychain = keychain

    def _provider_route(self, task: str) -> Route:
        return route_for(task)

    def resolve(self) -> dict | None:
        """返回当前生效配置 {provider,api_key,model,base_url}；无则返回 None（走 mock）。"""
        if self._keychain:
            r = self._keychain.current()
            if r:
                return r
        p = self.settings.default_provider
        key = self.settings.api_keys.get(p)
        if key:
            return {
                "provider": p, "api_key": key,
                "model": self.settings.default_model,
                "base_url": self.settings.base_urls.get(p, self.settings.openai_compat_base_url),
            }
        return None

    def mode(self) -> str:
        return "openai-compat" if self.resolve() else "mock"

    async def complete(self, *, task: str, system: str, user: str, max_tokens: int | None = None,
                       temperature: float | None = None) -> str:
        route = self._provider_route(task)
        if temperature is not None:  # 文风可覆盖默认温度
            route = Route(temperature=temperature, max_tokens=route.max_tokens)

        cfg = self.resolve()
        if cfg is None:
            mock = MockLLM()
            return await mock.complete(task=task, system=system, user=user,
                                       max_tokens=max_tokens or route.max_tokens,
                                       temperature=route.temperature)

        llm = OpenAICompatLLM(
            base_url=cfg["base_url"] or self.settings.openai_compat_base_url,
            api_key=cfg["api_key"],
            model=cfg["model"],
            route=route,
            timeout=self.settings.llm_timeout,
        )
        return await llm.complete(system=system, user=user, max_tokens=max_tokens)

    def stream(self, *, task: str, system: str, user: str, max_tokens: int | None = None,
               temperature: float | None = None):
        """流式版：返回异步迭代器，逐个增量产出文本。"""
        route = self._provider_route(task)
        if temperature is not None:
            route = Route(temperature=temperature, max_tokens=route.max_tokens)

        cfg = self.resolve()
        if cfg is None:
            return MockLLM().stream(task=task, system=system, user=user,
                                    max_tokens=max_tokens or route.max_tokens,
                                    temperature=route.temperature)

        llm = OpenAICompatLLM(
            base_url=cfg["base_url"] or self.settings.openai_compat_base_url,
            api_key=cfg["api_key"],
            model=cfg["model"],
            route=route,
            timeout=self.settings.llm_timeout,
        )
        return llm.stream(system=system, user=user, max_tokens=max_tokens)