"""本地 mock LLM：无密钥 / 测试时的降级实现。

关键：mock 输出必须是真实实现同协议的"文本"，由上层 DirectionGenerator / WriterAgent 解析，
保证"有 key 走真模型、无 key 走 mock"走同一套消费路径。
"""
from __future__ import annotations

import json
from typing import Any

from app.schemas import Card, CardLabel, Rarity

MOCK_DIRECTION_CARDS: list[dict[str, Any]] = [
    {
        "card_id": "mock-night-1",
        "title": "夜雨敲门",
        "label": "EVENT",
        "rarity": "R",
        "weight": 40,
        "content": "雨夜有人敲响旅店的门，指名要找主角。是久别重逢，还是暗处追兵？",
    },
    {
        "card_id": "mock-artist-2",
        "title": "落魄画师",
        "label": "MEETING",
        "rarity": "SR",
        "weight": 25,
        "content": "街角画师总在画同一座不存在的城，他认出了主角身上的一件旧物。",
        "risk_balance": {"tension": 6, "suggested_turn": "画师揭晓关于主角过去的线索"},
    },
    {
        "card_id": "mock-letter-3",
        "title": "无名密信",
        "label": "FORESHADOW",
        "rarity": "N",
        "weight": 60,
        "content": "一封没有落款的信，笔迹却异常熟悉，落款日期是明天。",
    },
    {
        "card_id": "mock-gate-4",
        "title": "城门口的天光",
        "label": "SCENE",
        "rarity": "R",
        "weight": 35,
        "content": "清晨城门口出现异象，人群骚动，兵士逐个盘查过客。",
    },
]

VALIDATE_CARDS: list[Card] = [Card.model_validate(c) for c in MOCK_DIRECTION_CARDS] or [
    Card(
        card_id="mock-fallback-0",
        title="命运的回响",
        label=CardLabel.FORESHADOW,
        rarity=Rarity.N,
        weight=100,
        content="一个似曾相识的征兆浮现，故事缓缓转向新的分岔。",
    )
]

_DRAFT_TEMPLATES = [
    "他把门推开一条缝，冷风携着雨丝灌进来。屋外那人立在檐下，斗笠压得很低，只露出一截腰间的旧铜牌。主角的目光落在那铜牌上，瞳孔骤然一缩——那是只有他自己才知道的暗记。",
    "酒旗在风里翻卷，街上的人潮忽然让开一条道。马队的尘土漫过青石板，战马上的人遥遥望过来，像在确认什么。主角缓缓放下酒杯，指节收紧了。",
    "夜灯昏黄。老画师停下手里的笔，盯着主角看了半晌，忽然低声说了句奇怪的话：“你左肩的旧伤……是一把断刃留下的吧？”空气静下来，只剩炉火噼啪。",
    "信纸的边角已经泛黄，落款虽是明天，笔迹却像写于很多年前。主角心头一跳，那句几乎被遗忘的问话浮了上来——他究竟忘记了什么？",
]


def _mock_blueprint(user: str) -> dict:
    """无 key 时的占位蓝图：三段结构齐全，便于前端/测试看到完整字段。"""
    hint = _extract_hint(user)
    return {
        "world": {
            "rules": ["魔法受七日蚀月周期影响", "禁术会反噬施术者"],
            "geography": "一座被雾海环绕的旧城，四周是失落的遗迹",
            "power_system": "以「记忆刻印」为力量的来源",
            "factions": ["守刻人公会", "流浪刻师"],
            "constraints": ["刻印不可逆", "每次刻印都会消耗记忆"],
        },
        "history": [
            {"era": "三百年前", "event": "大封城", "impact": "旧城与外界隔绝，记忆成为货币"},
            {"era": "一百年前", "event": "刻印之乱", "impact": "守刻人掌握城邦权力"},
        ],
        "characters": [
            {"name": "阿刻", "role": "protagonist", "goal": "找回失去的记忆刻印",
             "inner_need": "被认可与记起", "flaw": "不敢直面过去的背叛",
             "trait": "沉默寡言但记性极好"},
            {"name": "刻影", "role": "supporter", "goal": "推翻守刻人", "inner_need": "真相",
             "flaw": "偏执", "trait": "流浪刻师，身手矫健"},
        ],
        "outline": [
            {"no": 1, "type": "act", "title": "第一卷·刻雾", "goal": "阿刻意外得到一枚不该存在的刻印"},
            {"no": 2, "type": "chapter", "title": "首章·雨夜来客", "goal": "引入阿刻与刻影的相遇",
             "foreshadow": "主角左肩有旧伤"},
            {"no": 3, "type": "chapter", "title": "次章·旧城底图的裂缝", "goal": "发现古城地底的入口",
             "foreshadow": "一枚无名令牌"},
        ],
    }


def _extract_hint(user: str) -> str:
    # 从用户 prompt 里取一行（决策摘要），用于 mock 正文贴合方向
    for line in user.splitlines():
        line = line.strip()
        if line and len(line) >= 2:
            return line[:40]
    return user[:40]


class MockLLM:
    """本地占位实现：direction 返回合法 JSON 卡池，init/draft 返回占位文本。"""

    def __init__(self, provider: str = "mock") -> None:
        self.provider = provider
        self.mode = "mock"

    async def complete(self, *, task: str, system: str, user: str, max_tokens: int = 800,
                       temperature: float | None = None) -> str:
        if task == "direction":
            return json.dumps(MOCK_DIRECTION_CARDS, ensure_ascii=False)
        if task == "blueprint":
            return json.dumps(_mock_blueprint(user), ensure_ascii=False)
        if task == "init":
            return f"【世界观与大纲占位】围绕主题「{user[:40]}」铺开：三分一设定，三分一历史，三分一伏笔。"
        # draft：贴合 user 提示中的方向摘要
        hint = _extract_hint(user)
        idx = abs(hash(hint)) % len(_DRAFT_TEMPLATES)
        prose = _DRAFT_TEMPLATES[idx]
        if task == "consistency":
            return '{"passed": true, "issues": []}'
        return prose + f"\n\n（AI 正文占位：基于　「{hint}」　生成，接入真实模型后替换）"