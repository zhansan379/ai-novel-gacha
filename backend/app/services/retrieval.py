"""检索画像（检索触发编排）：开书一次判定 + 按画像的网络预取。

为什么需要：
- 旧逻辑用"专有名词点名"（知识库）和"拉丁英文 token"（联网）判定要不要检索，
  对「山西下井」「煤矿」这类中文职业/地域/主题题材是双盲区——既不开知识库也不联网。
- 这里改为：开书时对前提+简介做**一次**结构化判定，产出四维度画像 + 中文专题清单，
  之后网络预取与正文增量联网都按画像决定。判定走 LLM，失败回退确定性关键词兜底，
  绝不阻塞开书；未配置搜索密钥时自动降级为纯召回。

分层：
- ProfileDeterminer.determine —— 开书一次，产出 RetrievalProfile（存 story.retrieval_profile）。
- prefetch —— 开书一次，按画像 topics 并行网络预取，结果并入 story.grounding。
- 正文增量联网由 _ground_decision 读取画像的 timeliness 决定，本模块不参与正文路径。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.services.jsonparse import loads_coerce

_PROFILE_SYSTEM = """你是小说题材分析器。根据一本小说的前提与简介，判断它需要哪些外部资料来保证专业与真实，只输出一个 JSON 对象，不要任何解释或 markdown。

判定四维度：
- real_world：真实事实密度。历史/战争/真实事件改编/地域纪实 → high；都市日常/职场 → low；纯架空玄幻 → none。可取值 none|low|high。
- profession：专业深度。涉及医学/法律/军事/金融/采掘/职场等专业流程则 high，并列出 domains（涉及的专业领域，中文名词）。
- timeliness：时效性。只有当剧情核心依赖"当下正在变的现实"（最新政策/在售科技产品/时事/热搜/近期赛果/行业当下动态）才 high；借用稳定设定（古代制度、稳定规程）一律 low 或 none。
- continuity：设定连续性。长篇/系列/群像/伏笔较多的 → high；短篇 → low。
- topics：真正需要联网查证的中文专题清单（每项 {label, kind}，kind 取 professional|historical|technical|regional|timely 之一）。纯架空且无需查证时为 []。
- require_web：topics 非空即 true，否则 false。

示例输入「我在山西下井的日子」→ real_world high、profession 含采掘、timeliness low、topics 含「煤矿井工开采流程」「井下安全规程·瓦斯·透水防治」「山西煤炭工业概况」。"""


@dataclass
class RetrievalProfile:
    """本书记录的检索画像。merits_dict() 供落库到 story.retrieval_profile。"""

    real_world: str = "low"
    profession: dict = field(default_factory=lambda: {"level": "none", "domains": []})
    timeliness: str = "low"
    continuity: str = "low"
    topics: list = field(default_factory=list)   # [{label, kind}]
    require_web: bool = False

    def merits_dict(self) -> dict:
        """落库形态（JSON 可序列化，供 snapshot/import 往返）。"""
        return {
            "real_world": self.real_world,
            "profession": {"level": self.profession.get("level", "none"),
                           "domains": list(self.profession.get("domains") or [])},
            "timeliness": self.timeliness,
            "continuity": self.continuity,
            "topics": [{"label": t.get("label", ""), "kind": t.get("kind", "")} for t in self.topics],
            "require_web": bool(self.require_web),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RetrievalProfile":
        if not data:
            return cls()
        ps = data.get("profession") or {}
        return cls(
            real_world=str(data.get("real_world") or "low"),
            profession={"level": str(ps.get("level") or "none"), "domains": list(ps.get("domains") or [])},
            timeliness=str(data.get("timeliness") or "low"),
            continuity=str(data.get("continuity") or "low"),
            topics=[{"label": t.get("label", ""), "kind": t.get("kind", "")}
                    for t in (data.get("topics") or []) if (t or {}).get("label")],
            require_web=bool(data.get("require_web")),
        )


# 关键词兜底：确定性、无 LLM、不阻塞。每一组是 (触发词, 画像调整, 专题清单)。
# 归纳尽量克制：宁可少给专题，也不把无关题材误判成高资料需求。
_KEYWORD_RULES: list[tuple[tuple[str, ...], dict, list[tuple[str, str]]]] = [
    (("煤矿", "矿井", "下井", "矿工", "采掘", "瓦斯", "矿难", "煤老板"),
     {"real_world": "high", "profession": ["采掘", "安全规程"]},
     [("煤矿井工开采主要流程", "professional"), ("井下安全规程·瓦斯·透水防治", "professional")]),
    (("医生", "医院", "急诊", "手术", "护士", "医学", "诊断", "用药", "主治"),
     {"real_world": "high", "profession": ["医疗"]},
     [("医疗诊疗流程与临床用药规范", "professional")]),
    (("律师", "法庭", "诉讼", "法官", "检察院", "法医", "刑罚", "判决", "案子"),
     {"real_world": "high", "profession": ["法律", "刑侦"]},
     [("刑事/民事诉讼流程与法律条文框架", "professional")]),
    (("刑侦", "破案", "侦探", "悬疑", "密室", "命案", "证据链", "审讯"),
     {"real_world": "high", "profession": ["刑侦"]},
     [("刑侦流程·证据链·法医鉴定", "professional")]),
    (("金融", "股票", "投资", "交易", "基金", "融资", "上市", "信贷", "理财"),
     {"real_world": "high", "profession": ["金融"]},
     [("金融产品与监管框架", "professional")]),
    (("历史", "古代", "王朝", "朝代", "三国", "大唐", "大宋", "明清", "民国", "抗战", "长征"),
     {"real_world": "high", "timeliness": "none"},
     [("古代/历史朝代的制度·服饰·货币·地理", "historical")]),
    (("战争", "战场", "军营", "部队", "战役", "军官", "武器", "战略"),
     {"real_world": "high", "profession": ["军事"]},
     [("军事编制·武器·战术·战役背景", "historical")]),
    (("职场", "公司", "办公室", "官场", "体制", "升职", "创业", "商战", "收购", "CEO"),
     {"real_world": "high", "profession": ["职场"]},
     [("行业流程·公司架构·职级体制", "professional")]),
    (("近未来", "未来", "人工智能", "AI", "机器人", "元宇宙", "芯片", "航天"),
     {"real_world": "high", "timeliness": "high"},
     [("相关技术当下的真实现状与代表性产品", "technical")]),
    (("煤炭", "钢厂", "车间", "工厂", "车间", "流水线", "工人"),
     {"real_world": "high"},
     [("重工业行业作业流程与安全规范", "professional")]),
    (("真实", "纪实", "年代", "山村", "农村", "小镇", "地方"),
     {"real_world": "high"},
     []),
]


def _keyword_fallback(premise: str, synopsis: str) -> RetrievalProfile:
    """LLM 不可用/失败时的确定性兜底：按触发词产出保守画像与中文专题。"""
    text = f"{premise}\n{synopsis}"
    prof: dict = {"level": "none", "domains": []}
    timeliness = "low"
    continuity = "low"
    real_world = "low"
    topics: list[dict] = []
    seen: set[str] = set()
    for words, adj, topic_specs in _KEYWORD_RULES:
        if not any(w in text for w in words):
            continue
        if adj.get("real_world"):
            real_world = adj["real_world"] or real_world
        if adj.get("timeliness"):
            timeliness = adj["timeliness"]
        for dom in adj.get("profession") or []:
            if dom not in prof["domains"]:
                prof["domains"].append(dom)
        for label, kind in topic_specs:
            if label not in seen:
                seen.add(label)
                topics.append({"label": label, "kind": kind})
    if prof["domains"]:
        prof["level"] = "high"
    # 长篇/系列无法从前提确定，保守给 low；仅识别明显群像/长篇词
    if any(w in text for w in ("系列", "长篇", "群像", "续", "卷")) and "篇" not in text:
        continuity = "high"
    return RetrievalProfile(
        real_world=real_world, profession=prof, timeliness=timeliness,
        continuity=continuity, topics=topics, require_web=bool(topics),
    )


class ProfileDeterminer:
    """一次 LLM 判定产出本书检索画像；LLM 关/失败回退关键词兜底。"""

    def __init__(self, gateway=None) -> None:
        self._gateway = gateway

    async def determine(self, premise: str, synopsis: str = "") -> RetrievalProfile:
        if settings.profiling_enabled and self._gateway is not None:
            try:
                raw = await self._gateway.complete(
                    task="retrieval-profile", system=_PROFILE_SYSTEM,
                    user=f"【小说前提】{premise}\n【小说简介】{synopsis}\n\nJSON：",
                )
                data = loads_coerce(raw)
                if isinstance(data, dict):
                    return self._normalize(data)
            except Exception:
                pass  # 判定失败不阻塞开书，回退关键词兜底
        return _keyword_fallback(premise, synopsis)

    @staticmethod
    def _normalize(data: dict[str, Any]) -> RetrievalProfile:
        prof = data.get("profession") or {}
        if isinstance(prof, str):  # 容忍把 profession 写成字符串
            prof = {"level": prof, "domains": []}
        prof = {
            "level": str(prof.get("level") or "none") if isinstance(prof, dict) else "none",
            "domains": list(prof.get("domains") or []) if isinstance(prof, dict) else [],
        }
        topics = []
        for t in (data.get("topics") or []):
            if isinstance(t, str):
                topics.append({"label": str(t), "kind": "professional"})
            elif isinstance(t, dict) and (t.get("label") or "").strip():
                topics.append({"label": str(t["label"]).strip(),
                               "kind": str(t.get("kind") or "professional")})
        rw = str(data.get("real_world") or "low")
        tl = str(data.get("timeliness") or "low")
        ct = str(data.get("continuity") or "low")
        return RetrievalProfile(
            real_world=rw if rw in ("none", "low", "high") else "low",
            profession=prof,
            timeliness=tl if tl in ("none", "low", "high") else "low",
            continuity=ct if ct in ("none", "low", "high") else "low",
            topics=topics[: settings.profiling_max_topics],
            require_web=bool(topics),
        )


async def prefetch(profile: RetrievalProfile, web) -> list[str]:
    """按画像 topics 并行网络预取（开书一次）。web by enabled=False / 无 key → 返回空，不联网。

    返回带来源标签的"专业检索『专题』：摘要"事实行，供并入 story.grounding。
    任一专题检索失败静默，不阻断开书。
    """
    if web is None or not getattr(web, "enabled", False) or not profile.require_web:
        return []
    tasks = [asyncio.create_task(web.search(t["label"])) for t in profile.topics]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    facts: list[str] = []
    for topic, res in zip(profile.topics, results):
        if isinstance(res, BaseException) or not res:
            continue
        label = (topic.get("label") or "").strip()
        facts.append(f"专业检索『{label}』：{res}")
    return facts