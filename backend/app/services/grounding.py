"""真实世界事实基座：Chroma 向量检索 + 可选联网补充，供生成前注入。

为什么需要：
- 前提里一旦出现真实人物（如刘强东）或知名技术产品（如 Claude Code），
  模型若没有事实可依就会靠记忆/网文套路瞎编（例如虚构"2023年刘强东辞职"，
  或把 Claude Code 写成"藏机密的记事应用"）。
- 事实的唯一权威来源是 Chroma 向量库（app/services/vector_kb.py）。生成前对前提+简介
  做向量检索，命中即把事实注入 blueprint / direction / writer 的 prompt，约束模型尊重真实。
- 向量库未覆盖的中文职业/地域/主题题材，走检索画像（services/retrieval.py）判定并按专题
  网络预取（默认关闭，需配置 SEARCH_API_KEY）——不再本方法内自动联网。

只对"命中真实实体"的故事启用检索；纯架空书 zero 注入，不增加延迟。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import Settings

from .vector_kb import KNOWN_ENTITIES, ChromaKBFacade, build_chroma_facade


def _named_in(text_lower: str, entity: str) -> bool:
    """当前文本是否点到该真实实体的名字（拉丁/中文都忽略大小写与空白差异）。"""
    t = re.sub(r"\s+", "", text_lower)
    e = re.sub(r"\s+", "", (entity or "").lower())
    return bool(e) and e in t


def filter_grounding(text: str, lines: list[str]) -> list[str]:
    """读时过滤已存的事实行：只留那些"实体名真正出现在故事文本里"的行。

    用于让此前误注入的事实立即从界面消失（老故事不必重建）；新故事创建时已由
    resolve 的门槛把关，这里对它们是无操作的。
    """
    t = re.sub(r"\s+", "", (text or "").lower())
    out: list[str] = []
    for raw in lines:
        stripped = raw.lstrip("•·").strip()
        if not stripped:
            continue
        if stripped.startswith("专业检索"):  # 画像预取的职业/地域/专业事实，属本书显式需求，保留
            out.append(raw)
            continue
        if stripped.startswith("网络检索"):
            m = re.search(r"『([^』]+)』", stripped)
            token = (m.group(1) if m else "").replace(" ", "")
            if token and token.lower() in t:
                out.append(raw)
            continue
        name = re.split(r"[：:]", stripped, 1)[0].strip()
        if name and re.sub(r"\s+", "", name.lower()) in t:
            out.append(raw)
    return out


def filter_real_entity_history(text: str, history: list[dict]) -> list[dict]:
    """读时过滤世界历史线：书里没点任何真实实体时，剔除历史线中混入的真实人物/公司条目。

    免得在纯架空/奇幻故事的历史线里出现"刘强东1998年创办京东"这类被误注入的史实。
    """
    t = re.sub(r"\s+", "", (text or "").lower())
    named = {re.sub(r"\s+", "", e.lower()) for e in KNOWN_ENTITIES if _named_in(t, e)}
    if named:
        return history  # 书里确实点了真实实体，历史线交给作者自洽，不越权删除
    out: list[dict] = []
    for h in history:
        joined = re.sub(r"\s+", "", "".join(str(h.get(k, "")) for k in ("era", "event", "impact")).lower())
        if any(e in joined for e in {re.sub(r"\s+", "", x.lower()) for x in KNOWN_ENTITIES}):
            continue
        out.append(h)
    return out

# 命中的真实事实都挂在这一约束标签下，防止被当作虚构。声明"高于简介"：当简介/剧情与真实文献冲突时，
# 模型须以事实基座为准，而不是回读那些凭记忆虚构的简介。
GROUNDING_LABEL = ("【真实事实基座（须尊重，高于简介）】以下事实来自内置知识库或联网检索，是可核实的真实信息。\n"
                   "若与故事简介或剧情发生冲突，一律以本条真实事实为准。剧情可在其上展开；若情节必须与"
                   "真实历史/真实产品冲突，须明确写成架空改写并在叙事中暗示，不得把虚构当作已发生的现实。")


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
        q = query  # 不再附加"简介 是什么"：那会把结果压成辞典型/百科解释，冲掉叙事性的民间掌故（如人物早年求学经历）
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
        for r in results[:3]:
            c = (r.get("content") or "").strip()[:400]
            if c:
                parts.append(c)
        if not parts:
            return None
        return "；".join(parts)[:900]


class GroundingService:
    def __init__(self, *, vector: ChromaKBFacade | None = None,
                 web: WebSearch | None = None) -> None:
        self._vector = vector
        self._web = web

    async def resolve(self, premise: str, synopsis: str = "") -> GroundingResult:
        """知识库实体召回（离线、快）：只对当前文本真正点名了的真实实体注入事实。

        网络检索已改由检索画像(services/retrieval.py)驱动，不再由本方法内的启发式触发，
        避免「山西下井」「煤矿」这类中文职业/地域/主题题材落入检索盲区。
        """
        text = f"{premise}\n{synopsis}"
        res = GroundingResult()
        hits = self._vector.query(text) if self._vector is not None else []
        lower = text.lower()
        for item in hits:
            ent = (item["entity"] or "").strip()
            # 阈值判断：只有当当前文本真正点到该真实实体的名字才注入。
            # 纯架空书并未点名任何真实实体 → 天然 zero 注入，不再把无关履历/守则塞进剧情与历史线。
            if not ent or not _named_in(lower, ent):
                continue
            fact = item["fact"]
            res.facts.append(f"• {fact if '：' in fact else ent + '：' + fact}")
            if ent not in res.labels:
                res.labels.append(ent)
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