"""真实世界事实基座：Chroma 向量检索 + 可选联网补充，供生成前注入。

为什么需要：
- 前提里一旦出现真实人物（如刘强东）或知名技术产品（如 Claude Code），
  模型若没有事实可依就会靠记忆/网文套路瞎编（例如虚构"2023年刘强东辞职"，
  或把 Claude Code 写成"藏机密的记事应用"）。
- 事实的唯一权威来源是 Chroma 向量库（app/services/vector_kb.py）。生成前对前提+简介
  做向量检索，命中即把事实注入 blueprint / direction / writer 的 prompt，约束模型尊重真实。
- 向量库未覆盖的拉丁/产品类实体，可选用联网检索补充（默认关闭，需配置 SEARCH_API_KEY）。

只对"命中真实实体"的故事启用检索；纯架空书 zero 注入，不增加延迟。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import Settings

from .vector_kb import ChromaKBFacade, build_chroma_facade

# 常见 ASCII 噪声词，不作为联网检索候选
_STOP = {
    "ai", "app", "ui", "url", "api", "http", "https", "www", "com", "cn", "org", "net",
    "id", "html", "git", "sse", "json", "pdf", "txt", "img", "etc", "one", "two", "get",
    "set", "use", "new", "old", "the", "and", "for", "with", "from", "this", "that", "you",
    "your", "our", "his", "her", "its", "are", "was", "not", "but", "then", "when", "yuan",
}

# 命中的真实事实都挂在这一约束标签下，防止被当作虚构
GROUNDING_LABEL = ("【真实事实基座（须尊重）】以下事实来自内置知识库或联网检索，是可核实的真实信息。"
                   "剧情可在其上展开；若情节必须与真实历史/真实产品冲突，须明确写成架空改写并在叙事中"
                   "暗示，不得把虚构当作已发生的现实。")


@dataclass
class GroundingResult:
    facts: list[str] = field(default_factory=list)   # 事实行（含实体名），供注入
    labels: list[str] = field(default_factory=list)  # 命中实体名


class WebSearch:
    """可选联网检索（默认 Tavily）。未配置 API Key 时 enabled=False，自动只走 Chroma。"""

    def __init__(self, *, api_key: str, provider: str = "tavily",
                 max_queries: int = 2, timeout: float = 15.0) -> None:
        self.api_key = api_key
        self.provider = provider
        self.max_queries = max_queries
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str) -> str | None:
        q = f"{query} 简介 是什么"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "tavily":
                    res = await client.post("https://api.tavily.com/search", json={
                        "api_key": self.api_key, "query": q,
                        "search_depth": "basic", "max_results": 3,
                        "include_answer": True, "topic": "general",
                    })
                    if res.status_code >= 400:
                        return None
                    data = res.json()
                else:
                    data = {}
        except Exception:  # 检索失败不阻断主流程，回落向量库
            return None
        results = data.get("results") or []
        parts = []
        ans = data.get("answer")
        if ans:
            parts.append(str(ans).strip())
        for r in results[:2]:
            c = (r.get("content") or "").strip()[:300]
            if c:
                parts.append(c)
        if not parts:
            return None
        return "；".join(parts)[:500]


class GroundingService:
    def __init__(self, *, vector: ChromaKBFacade | None = None,
                 web: WebSearch | None = None) -> None:
        self._vector = vector
        self._web = web

    @staticmethod
    def _unresolved_tokens(text: str, labels: set[str]) -> list[str]:
        """向量库未覆盖的拉丁/产品类词：作为联网检索候选（多数产品/公司是拉丁拼写）。"""
        used = {x.lower() for x in labels}
        toks = re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{2,30}", text)
        out = []
        seen = set()
        for t in toks:
            k = t.lower().strip("._-")
            if k in _STOP or k in used:
                continue
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    async def resolve(self, premise: str, synopsis: str = "") -> GroundingResult:
        text = f"{premise}\n{synopsis}"
        res = GroundingResult()
        hits = self._vector.query(text) if self._vector is not None else []
        for item in hits:
            fact = item["fact"]
            res.facts.append(f"• {fact if '：' in fact else item['entity'] + '：' + fact}")
            if item["entity"] and item["entity"] not in res.labels:
                res.labels.append(item["entity"])

        web = self._web
        if web and web.enabled:
            for token in self._unresolved_tokens(text, set(res.labels))[:web.max_queries]:
                summary = await web.search(token)
                if summary:
                    res.facts.append(f"• 网络检索『{token}』：{summary}")
                    if token not in res.labels:
                        res.labels.append(token)
        return res

    def facts_text(self, res: GroundingResult) -> str:
        """生成注入 prompt 的事实块（无命中则空串，不干扰纯架空书）。"""
        if not res.facts:
            return ""
        return GROUNDING_LABEL + "\n" + "\n".join(res.facts)


def make_grounding(settings: Settings, gateway=None) -> GroundingService:
    """按配置组装：Chroma 向量库（ngram 默认 / llm 可选）+ 可选联网检索。"""
    vector = None
    if gateway is not None and settings.embedding_mode == "llm" and settings.embedding_model:
        cfg = gateway.resolve()
        if cfg and cfg.get("api_key") and cfg.get("base_url"):
            vector = build_chroma_facade(
                path=settings.chroma_path, mode="llm",
                embed={"base_url": cfg["base_url"], "api_key": cfg["api_key"],
                       "model": settings.embedding_model},
            )
    if vector is None:
        vector = build_chroma_facade(path=settings.chroma_path, mode="n-gram")
    web = WebSearch(api_key=settings.search_api_key,
                    provider=settings.search_provider,
                    timeout=settings.search_timeout)
    return GroundingService(vector=vector, web=web)