"""OpenAI 兼容提供商实现（httpx，无需 openai 依赖，兼容任意 /chat/completions）。"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.llm.routing import Route

from .errors import ModelError, QuotaError


def completions_url(base_url: str) -> str:
    """把用户填写的 Base URL 归一到完整 chat/completions 端点。

    兜底处理：即便用户贴的是完整端点（结尾已带 /chat/completions），
    也不再重复拼接，避免生成 /chat/completions/chat/completions 这类 404 路径。
    """
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def embeddings_url(base_url: str) -> str:
    """从 Base URL 推导 /embeddings 端点（OpenAI 兼容）。"""
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    elif base.endswith("/completions"):
        base = base[: -len("/completions")]
    return f"{base.rstrip('/')}/embeddings"


class OpenAICompatLLM:
    def __init__(self, *, base_url: str, api_key: str, model: str, route: Route, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoint = completions_url(self.base_url)
        self.api_key = api_key
        self.model = model
        self.route = route
        self.timeout = timeout
        self.mode = "openai-compat"

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """调用 OpenAI 兼容 /embeddings 端点，返回向量列表（供 Chroma LLM embedding 校验/使用）。"""
        url = embeddings_url(self.endpoint)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": model or self.model, "input": list(texts)}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code >= 400:
                    raise ModelError(f"embedding 返回 {res.status_code}: {res.text[:200]}")
                data = res.json()
                return [item["embedding"] for item in data["data"]]
        except httpx.HTTPError as exc:
            raise ModelError(f"embedding 请求失败（{type(exc).__name__}）：{str(exc).strip()}") from exc

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
                res = await client.post(self.endpoint, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            detail = str(exc).strip()
            msg = f"模型请求失败：无法访问 {self.endpoint}（{type(exc).__name__}）"
            if detail:
                msg += f"：{detail}"
            raise ModelError(msg) from exc

        if res.status_code == 402 or res.status_code == 429:
            raise QuotaError(f"配额/限流({res.status_code}): {res.text[:200]}")
        if res.status_code >= 400:
            raise ModelError(f"模型返回 {res.status_code}: {res.text[:300]}")

        data = res.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError(f"响应解析失败: {res.text[:300]}") from exc

    async def stream(self, *, system: str, user: str, max_tokens: int | None = None) -> AsyncIterator[str]:
        """SSE 流式：逐 token 增量产出正文。"""
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.route.temperature,
            "max_tokens": max_tokens or self.route.max_tokens,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.endpoint,
                                          json=payload, headers=headers) as res:
                    if res.status_code == 402 or res.status_code == 429:
                        body = await res.aread()
                        raise QuotaError(f"配额/限流({res.status_code}): {body[:200]}")
                    if res.status_code >= 400:
                        body = await res.aread()
                        raise ModelError(f"模型返回 {res.status_code}: {body[:300]}")
                    async for line in res.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {}).get("content", "")
                        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                            continue
                        if delta:
                            yield delta
        except httpx.HTTPError as exc:
            detail = str(exc).strip()
            msg = f"模型请求失败：无法访问 {self.endpoint}（{type(exc).__name__}）"
            if detail:
                msg += f"：{detail}"
            raise ModelError(msg) from exc