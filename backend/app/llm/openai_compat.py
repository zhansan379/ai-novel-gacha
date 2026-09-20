"""OpenAI 兼容提供商实现（httpx，无需 openai 依赖，兼容任意 /chat/completions）。"""
from __future__ import annotations

import httpx

from app.llm.routing import Route

from .errors import ModelError, QuotaError


class OpenAICompatLLM:
    def __init__(self, *, base_url: str, api_key: str, model: str, route: Route, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.route = route
        self.timeout = timeout
        self.mode = "openai-compat"

    async def complete(self, *, system: str, user: str, max_tokens: int | None = None) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.route.temperature,
            "max_tokens": max_tokens or self.route.max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ModelError(f"模型请求失败: {exc}") from exc

        if res.status_code == 402 or res.status_code == 429:
            raise QuotaError(f"配额/限流({res.status_code}): {res.text[:200]}")
        if res.status_code >= 400:
            raise ModelError(f"模型返回 {res.status_code}: {res.text[:300]}")

        data = res.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError(f"响应解析失败: {res.text[:300]}") from exc