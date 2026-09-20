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
- 若提示词里的【当前设定状态】含真实事实基座，且与故事简介冲突，一律以真实事实为准
  基于故事设定与已确定的剧情方向，续写一段中文正文（700~1000 字）。只输出正文本身，不要标题、不要解释。
"""

_OPENING_GROUNDING = """[开篇落地要求 - 本段是全书第一拍，必须让读者立刻进入这个世界，无一可省]
- 主角是谁、叫什么、当前身份与处境；若前提含穿越/重生/异世/超凡等特殊出身，写出处与来龙去脉
- 当前所处时代与地点：让读者能感到这是哪个年代、哪座城市/场景
- 前提里的核心设定与特殊要素，要做成可见的画面落地（它是什么、此刻如何存在、当前能为剧情起到什么作用）
- 第一个可感知的具体画面与处境，让读者立刻进入这个世界，而不是凭空开始的日常流水账
全部按叙事融入交代，禁止一整段干巴巴的设定罗列。"""

_METHODOLOGY = """[写作方法论：展示而非告知]
本段只对自己负责（局部真实），跨段铺垫与叙事走向由前文设定控制，不在本段硬塞。
- 1. 场景是感觉得到的，不是说得出的：每个关键场景至少从声音、尺度/数字、画面、人物动作、生存逻辑中取两样落地；不直呼“恐怖/神秘/重要”，让读者自己去感受。
- 2. 人物活在动作与对话里，不用标签：用具体动作、语气、生活细节刻画性格；不用“目光锐利如夜行猫”“微微一笑”“目光深邃”这类套话；旧伤、家变、宿怨等关键过往须先铺垫，禁止突然空降。
- 3. 因果要付代价，线索不白给：帮助与信物须有动机、隐瞒或代价，不能无缘白送；“此物藏有奥秘”须用异象/异感证明，不能只靠台词交代；重大抉择要带出追兵、风险、牺牲等真实阻力。
- 4. 语言有节奏：长短句交错，动词准确；禁堆副词/形容词，忌文白夹杂。避免填充词：仿佛、似乎、缓缓、微微、一丝、闪过。
- 5. 一致性：人名、地名、设定前后统一，杜绝混用。
- 6. 背景要透口，不设路障：借角色视角、现场环境、自然对白让读者进入世界氛围与设定，不假设读者已知背景；但禁止整段设定说明或名词堆砌，交代点到即止、融入叙事。
"""


def _direction_plan(direction: DirectionSpec) -> str:
    """把所选卡的因果规划拼成一段显式要求，喂给正文作者。"""
    plan = ""
    if getattr(direction, "cause", None):
        plan += f"\n【事件诱因（必须先交代如何发生/如何被察觉）】{direction.cause}"
    if getattr(direction, "aftermath", None):
        plan += f"\n【事件后果（落定后各方反应与影响，要写到正文里）】{direction.aftermath}"
    if getattr(direction, "suspense", None):
        plan += f"\n【本拍悬念（结尾留给读者的钩子，可留白但须指向它）】{direction.suspense}"
    if getattr(direction, "risk_balance", None):
        rb = direction.risk_balance
        plan += f"\n【张力要求】{rb.tension}/10，转折建议：{rb.suggested_turn}"
    return plan


class WriterAgent:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def _system(self, style: StyleProfile) -> str:
        forbid = "；".join(f"避免{tag}" for tag in style.forbidden) if style.forbidden else ""
        style_txt = f"{style.system_prompt}\n{forbid}" if forbid else style.system_prompt
        return _WRITER_SYSTEM + "\n[文风要求]" + style_txt + "\n" + _METHODOLOGY

    async def generate(self, *, premise: str, synopsis: str, direction: DirectionSpec | None,
                       tail: str = "", style_profile_id: str | None = None, context: str = "") -> str:
        style = get_style(style_profile_id)
        system = self._system(style)
        ctx = (f"\n【当前设定状态（须尊重；含真实事实且与简介冲突时以事实为准）】\n{context}"
               if context else "")
        if direction is None:
            return await self._gateway.complete(
                task="draft", system=system + _OPENING_GROUNDING, temperature=style.temperature,
                user=(f"{ctx}\n【故事前提】{premise}\n【故事简介】{synopsis}\n请续写开篇正文："),
            )
        plan = _direction_plan(direction)
        extra = f"\n【场景提示】{direction.scene}" if direction.scene else ""
        tail_seg = f"【上一段】{tail}\n" if tail else ""
        user = (
            f"{ctx}\n"
            f"【故事前提】{premise}\n"
            f"【故事简介】{synopsis}\n"
            f"{tail_seg}"
            f"【已确定方向】{direction.summary}{extra}{plan}\n"
            "请按此方向续写正文："
        )
        return await self._gateway.complete(task="draft", system=system, temperature=style.temperature, user=user)

    async def stream_generate(self, *, premise: str, synopsis: str,
                              direction: DirectionSpec | None, tail: str = "",
                              style_profile_id: str | None = None, context: str = "") -> AsyncIterator[str]:
        """流式续写：逐个增量产出正文（供 SSE）。"""
        style = get_style(style_profile_id)
        system = self._system(style)
        ctx = (f"\n【当前设定状态（须尊重；含真实事实且与简介冲突时以事实为准）】\n{context}"
               if context else "")
        if direction is None:
            user = f"{ctx}\n【故事前提】{premise}\n【故事简介】{synopsis}\n请续写开篇正文："
            system = system + _OPENING_GROUNDING
        else:
            plan = _direction_plan(direction)
            extra = f"\n【场景提示】{direction.scene}" if direction.scene else ""
            tail_seg = f"【上一段】{tail}\n" if tail else ""
            user = (
                f"{ctx}\n"
                f"【故事前提】{premise}\n"
                f"【故事简介】{synopsis}\n"
                f"{tail_seg}"
                f"【已确定方向】{direction.summary}{extra}{plan}\n"
                "请按此方向续写正文："
            )
        stream = self._gateway.stream(task="draft", system=system, user=user,
                                      temperature=style.temperature)
        async for chunk in stream:
            yield chunk

    def _compare_system(self, style: StyleProfile) -> str:
        forbid = "；".join(f"避免{tag}" for tag in style.forbidden) if style.forbidden else ""
        style_txt = f"{style.system_prompt}\n{forbid}" if forbid else style.system_prompt
        return "你是小说文风改写助手。严格按给定的文风要求改写正文。\n\n[文风要求]\n" + style_txt

    async def compare(self, text: str, style: StyleProfile) -> str:
        """用指定文风把同一段素材改写成一段小说正文（文风对比用）。"""
        user = (f"请将下面这段话改写成一段连贯、有画面感的小说正文，控制在 80~150 字，"
                f"只输出改写后的正文：\n\n{text}")
        return await self._gateway.complete(
            task="draft", system=self._compare_system(style),
            temperature=style.temperature, user=user,
        )