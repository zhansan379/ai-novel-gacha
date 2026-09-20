"""前置构建蓝图服务（BlueprintBuilder）：世界观 / 历史线 / 角色 / 伏笔种子。

不再产出"预设卷·章大纲"（大纲改为随剧情复盘，交由 timeline 表达）；初始伏笔
改由 foreshadow_seeds 直接提供。输出强 schema；模型返回无法解析时抛 ModelError，
由全局异常处理器规整成 502，不再静默回退占位。
"""
from __future__ import annotations

import json

from app.llm import LLMGateway
from app.llm.errors import ModelError

_BLUEPRINT_SYSTEM = """你是小说世界构建师。基于「前提 + 简介」，产出结构化设定：
世界观（简洁，只写与故事相关的部分）、历史线（过去的重大事件与成因）、
角色（主角外在目标/内在需求/缺点 + 一位配角）、伏笔种子（故事开头就该埋下、
指向后文转折的伏笔文案列表，2~4 条）。

伏笔种子必须由你根据本故事的前提与简介自行拟定，紧扣故事内核（人物过往、阵营秘密、
关键物证、悬念关系等），禁止照抄提示词里的例子。

严格只输出一个 JSON 对象，不要 Markdown、不要解释，按以下字段结构（示例值请用 … 占位，
不要照抄为具体内容）：
{
  "world": {"rules": ["…"], "geography": "…", "power_system": "…",
            "factions": ["…"], "constraints": ["…"]},
  "history": [{"era": "…", "event": "…", "impact": "…"}],
  "characters": [{"name":"…","role":"protagonist|supporter","goal":"外在目标",
                  "inner_need":"内在需求","flaw":"缺点","trait":"一句话特征"}],
  "foreshadow_seeds": ["…", "…"]
}
"""


def _parse_blueprint(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelError(f"蓝图响应不是合法 JSON：{raw[:200]}") from exc
    if not isinstance(data, dict):
        raise ModelError("蓝图响应非对象")
    for key in ("world", "history", "characters", "foreshadow_seeds"):
        if key not in data:
            raise ModelError(f"蓝图缺少字段: {key}")
    return data


class BlueprintBuilder:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def build(self, *, premise: str, synopsis: str) -> dict:
        user = f"【前提】{premise}\n【简介】{synopsis}\n请输出复合蓝图 JSON："
        raw = await self._gateway.complete(task="blueprint", system=_BLUEPRINT_SYSTEM, user=user)
        return _parse_blueprint(raw)