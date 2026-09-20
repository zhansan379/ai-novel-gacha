"""前置构建蓝图服务（BlueprintBuilder）：世界观 / 历史线 / 角色 / 卷·章大纲。

对应设计文档 §3「三段前置 + premise 公式」：开书先用 LLM 产出结构化设定，
再进入正文。输出强 schema；解析失败回退内置占位，保证稳定。
"""
from __future__ import annotations

import json

from app.llm import LLMGateway

_BLUEPRINT_SYSTEM = """你是小说世界构建师。基于「前提 + 简介」，用三段前置产出复合蓝图：
世界观（简洁，只写与故事相关的部分）、历史线（过去的重大事件与成因）、
角色（主角外在目标/内在需求/缺点 + 一位配角）、卷·章大纲（用三幕剧骨架组织卷与章）。

严格只输出一个 JSON 对象，不要 Markdown、不要解释：
{
  "world": {"rules": ["…"], "geography": "…", "power_system": "…",
            "factions": ["…"], "constraints": ["…"]},
  "history": [{"era": "…", "event": "…", "impact": "…"}],
  "characters": [{"name":"…","role":"protagonist|supporter","goal":"外在目标",
                  "inner_need":"内在需求","flaw":"缺点","trait":"一句话特征"}],
  "outline": [{"no":1,"type":"act","title":"第一卷","goal":"本卷目标"},
              {"no":2,"type":"chapter","title":"首章","goal":"本章目标","foreshadow":"伏笔"}]
}
"""


def _fallback(premise: str) -> dict:
    return {
        "world": {"rules": ["设定待展开"], "geography": "", "power_system": "",
                  "factions": [], "constraints": []},
        "history": [],
        "characters": [{"name": "主角", "role": "protagonist", "goal": "",
                        "inner_need": "", "flaw": "", "trait": ""}],
        "outline": [{"no": 1, "type": "act", "title": "第一卷", "goal": ""},
                    {"no": 2, "type": "chapter", "title": "首章", "goal": "",
                     "foreshadow": ""}],
    }


class BlueprintBuilder:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def build(self, *, premise: str, synopsis: str) -> dict:
        user = f"【前提】{premise}\n【简介】{synopsis}\n请输出复合蓝图 JSON："
        try:
            raw = await self._gateway.complete(task="blueprint", system=_BLUEPRINT_SYSTEM, user=user)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("蓝图响应非对象")
            for key in ("world", "history", "characters", "outline"):
                if key not in data:
                    raise ValueError(f"蓝图缺少字段: {key}")
            return data
        except Exception:
            return _fallback(premise)