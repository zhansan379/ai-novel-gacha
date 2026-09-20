"""WriterAgent：基于已确定方向续写正文（含去 AI 味 + 文风预设注入）。"""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.llm import LLMGateway
from app.schemas import DirectionSpec
from app.services.styles import StyleProfile, get_style

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

    def _system(self, style: StyleProfile) -> str:
        forbid = "；".join(f"避免{tag}" for tag in style.forbidden) if style.forbidden else ""
        style_txt = f"{style.system_prompt}\n{forbid}" if forbid else style.system_prompt
        return _WRITER_SYSTEM + "\n[文风要求]" + style_txt

    async def generate(self, *, premise: str, synopsis: str, direction: DirectionSpec | None,
                       tail: str = "", style_profile_id: str | None = None) -> str:
        style = get_style(style_profile_id)
        system = self._system(style)
        if direction is None:
            return await self._gateway.complete(
                task="draft", system=system, temperature=style.temperature,
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
        return await self._gateway.complete(task="draft", system=system, temperature=style.temperature, user=user)

    async def stream_generate(self, *, premise: str, synopsis: str,
                              direction: DirectionSpec | None, tail: str = "",
                              style_profile_id: str | None = None) -> AsyncIterator[str]:
        """流式续写：逐个增量产出正文（供 SSE）。"""
        style = get_style(style_profile_id)
        system = self._system(style)
        if direction is None:
            user = f"【故事前提】{premise}\n【故事简介】{synopsis}\n请续写开篇正文："
        else:
            extra = f"\n【场景提示】{direction.scene}" if direction.scene else ""
            user = (
                f"【故事前提】{premise}\n"
                f"【故事简介】{synopsis}\n"
                f"{f'【上一段】{tail}\n' if tail else ''}"
                f"【已确定方向】{direction.summary}{extra}\n"
                "请按此方向续写正文："
            )
        stream = self._gateway.stream(task="draft", system=system, user=user,
                                      temperature=style.temperature)
        async for chunk in stream:
            yield chunk