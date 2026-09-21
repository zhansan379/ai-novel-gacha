"""LLM Gateway：按当前用户/提供商调度到 OpenAI 兼容实现。

配置来源：该用户在前端"设置面板"所配的 Keychain（Key 按用户隔离，且不回传明文）。
不再回退到全局 env 配置——公网多用户 BYOK 场景下，每个用户必须用自己的 Key，
否则会互相共享管理员 Key。未配置时抛出明确错误，提示用户先完成接入。
消费方只调用 `gateway.complete(task, system, user)` / `gateway.stream(...)`，不感知具体实现。
"""
from __future__ import annotations

from app.config import Settings
from app.context import current_user_id
from app.llm.errors import ModelError
from app.llm.routing import Route, route_for
from app.services.keychain import Keychain

from .openai_compat import OpenAICompatLLM

_NOT_CONFIGURED = (
    "未配置模型服务：请先在“设置”面板填写服务商、模型名、Base URL 与 API Key 后重试。"
)


class LLMGateway:
    def __init__(self, settings: Settings, keychain: Keychain | None = None) -> None:
        self.settings = settings
        self._keychain = keychain

    def _provider_route(self, task: str) -> Route:
        return route_for(task)

    def resolve(self) -> dict | None:
        """返回当前用户在设置面板配置的 {provider,api_key,model,base_url}；无则返回 None。"""
        if self._keychain:
            return self._keychain.current(current_user_id.get() or "")
        return None

    def mode(self) -> str:
        return "openai-compat" if self.resolve() else "unconfigured"

    async def complete(self, *, task: str, system: str, user: str, max_tokens: int | None = None,
                       temperature: float | None = None) -> str:
        route = self._provider_route(task)
        if temperature is not None:  # 文风可覆盖默认温度
            route = Route(temperature=temperature, max_tokens=route.max_tokens)

        cfg = self.resolve()
        if cfg is None:
            raise ModelError(_NOT_CONFIGURED)

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
            raise ModelError(_NOT_CONFIGURED)

        llm = OpenAICompatLLM(
            base_url=cfg["base_url"] or self.settings.openai_compat_base_url,
            api_key=cfg["api_key"],
            model=cfg["model"],
            route=route,
            timeout=self.settings.llm_timeout,
        )
        return llm.stream(system=system, user=user, max_tokens=max_tokens)

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """调用当前生效服务的 /embeddings 端点，返回向量列表（LLM embedding 用）。"""
        cfg = self.resolve()
        if cfg is None:
            raise ModelError(_NOT_CONFIGURED)
        llm = OpenAICompatLLM(
            base_url=cfg["base_url"] or self.settings.openai_compat_base_url,
            api_key=cfg["api_key"],
            model=cfg["model"],
            route=route_for("embed"),
            timeout=self.settings.llm_timeout,
        )
        return await llm.embed(texts, model=model)