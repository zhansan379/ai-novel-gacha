"""WriterAgent：基于已确定方向续写正文（含去 AI 味文风约束）。"""
from __future__ import annotations

from app.llm import LLMGateway
from app.schemas import DirectionSpec

_WRITER_SYSTEM = """你是长篇小说的正文作者。
文风要求：
- 白描为主，在动作、神态、环境中推进，避免大段心理解释性独白
- 避免“理所当然”“值得一提的是”“转眼间”“简直”等 AI 腔与空泛总结
- 对话符合人物性格，不充当信息倾倒
- 结构紧凑、有画面感，每段在一个具体场景里推进
基于故事设定与已确定的剧情方向，续写一段中文正文（200~400 字）。只输出正文本身，不要标题、不要解释。
"""


class WriterAgent:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def generate(self, *, premise: str, synopsis: str, direction: DirectionSpec | None,
                       tail: str = "") -> str:
        if direction is None:
            return await self._gateway.complete(
                task="draft", system=_WRITER_SYSTEM,
                user=(f"【故事前提】{premise}\n【故事简介】{synopsis}\n请续写开篇正文："),
            )
        extra = f"\n【场景提示】{direction.scene}" if direction.scene else ""
        user = (
            f"【故事前提】{premise}\n"
            f"【故事简介】{synopsis}\n"
            f"{f'【上一段】{tail}\n' if tail else ''}"
            f"【已确定方向】{direction.summary}{extra}\n"
            "请按此方向续写正文："
        )
        return await self._gateway.complete(task="draft", system=_WRITER_SYSTEM, user=user)