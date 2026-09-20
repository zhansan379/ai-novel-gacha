"""一致性检查器：比对"已有设定"与"新正文"，输出冲突清单。

复用 LLM Gateway 的 consistency 任务（温度 0，最稳）。输出与接口契约一致：
{"passed": bool, "issues": [{"type","severity","fragment","reason"}]}
无 key / 解析失败时保守通过（返回空冲突）。
"""
from __future__ import annotations

import json

from app.llm import LLMGateway

_SYSTEM = """你是长篇小说的设定一致性审查员。比对"已有设定(前提+简介)"与"新生成的正文"，找出明显冲突：
如：角色已死却又说话、设定前后矛盾、时间线错乱、称谓/关系对不上。
只输出一个 JSON 对象，不要任何 Markdown 或说明：
{"passed": bool, "issues": [{"type":"CONTINUITY"|"FACT","severity":"critical"|"warning",
"fragment":"原文片段","reason":"冲突说明"}]}
无冲突时 passed 为 true，issues 为 []。"""


def _strip(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        # 去掉可能的 markdown 围栏
        lines = raw.strip("`").strip().splitlines()
        return "\n".join(lines[1:]) if lines else raw
    return raw


class ConsistencyChecker:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def check(self, *, premise: str, synopsis: str, passage: str,
                    facts: list[str] | None = None) -> dict:
        facts_txt = "\n".join(f"- {f}" for f in (facts or [])) or "（无既定事实清单）"
        user = (
            f"【已有设定】前提：{premise}\n简介：{synopsis}\n"
            f"【设定事实清单（须遵守）】\n{facts_txt}\n"
            f"【新生成正文】{passage}\n请输出 JSON："
        )
        try:
            raw = await self._gateway.complete(task="consistency", system=_SYSTEM, user=user, max_tokens=400)
            data = json.loads(_strip(raw))
            if not isinstance(data, dict):
                raise ValueError("响应非对象")
            data.setdefault("passed", True)
            data.setdefault("issues", [])
            return data
        except Exception:
            return {"passed": True, "issues": []}