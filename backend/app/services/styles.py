"""文风预设（StyleProfile）。

对应设计文档 §7：文风 = 一段注入 Writer system prompt 的约束 + 温度。
提供 ≥5 套内置预设；get_style 负责解析/兜底。内置预设是本团队编写（仿经典写法风格），
不复制任何第三方受版权约束的文案。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_STYLE_ID = "restrained"


class StyleProfile(BaseModel):
    id: str
    name: str
    description: str
    temperature: float = Field(default=0.8, ge=0.0, le=1.5)
    system_prompt: str  # 注入 Writer 的"文风要求"段落
    forbidden: list[str] = Field(default_factory=list)


def _p(pid: str, name: str, desc: str, temp: float, prompt: str, forbidden: list[str]) -> StyleProfile:
    return StyleProfile(id=pid, name=name, description=desc, temperature=temp,
                        system_prompt=prompt, forbidden=forbidden)


STYLE_PROFILES: dict[str, StyleProfile] = {
    "wuxia": _p(
        "wuxia", "金庸武侠", "词采凝练、古朴有韵味，动作开场、对白见人", 0.78,
        "语言古朴凝练，多成语与四字句，讲究意境与留白；动作先于情绪，对白简洁有锋芒；"
        "善用江湖语境（师承、恩怨、帮派名）；避免直白内心旁白。",
        ["现代网络用语", "西式长句", "口语化吐槽"],
    ),
    "urban": _p(
        "urban", "现代都市", "冷峻克制、贴近现实的都市叙事", 0.8,
        "用克制、观察式的中性语言写都市生活；细节落在手机、地铁、霓虹等现代物象；"
        "对话短促、潜台词多于直说；情绪通过物件与动作暗示。",
        ["古风词藻", "宏大渲染", "说教式独白"],
    ),
    "xianxia": _p(
        "xianxia", "玄幻修仙", "恢弘设定、境界体系、节奏明快", 0.82,
        "场景有仙侠与山的辽阔感；着力展示境界/法宝/灵力等设定但要带出行动；"
        "语言利落、有反讽余地；爽点明确、推进干脆。",
        ["平直叙述设定", "过密内心戏", "白话啰嗦"],
    ),
    "horror": _p(
        "horror", "悬疑克苏鲁", "压抑、未知、缓缓渗透的恐惧", 0.75,
        "用不确定性营造恐惧：模糊的视听细节、似曾相识的征兆、逐渐失控的叙事；"
        "省略主语或让话只说一半；节奏舒缓而紧绷，拒绝轻易解释。",
        ["直白惊吓", "完整解释", "阳光乐观"],
    ),
    "restrained": _p(
        "restrained", "沉稳冷峻", "白描为主、克制冷静、少修饰", 0.75,
        "以白描与动作推进，句式短而稳；少用形容词堆叠与解释性内心；"
        "情感借言行与沉默流露，绝不大段抒情。",
        ["空泛抒情", "堆砌修饰", "说教"],
    ),
}


def get_style(style_id: str | None) -> StyleProfile:
    return STYLE_PROFILES.get(style_id or DEFAULT_STYLE_ID, STYLE_PROFILES[DEFAULT_STYLE_ID])


def list_styles() -> list[dict]:
    return [
        {"id": s.id, "name": s.name, "description": s.description, "temperature": s.temperature,
         "forbidden": s.forbidden}
        for s in STYLE_PROFILES.values()
    ]