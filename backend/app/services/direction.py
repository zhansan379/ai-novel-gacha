"""DirectionGenerator：在分歧点调用 LLM 生成 3~5 张候选命运卡（强 schema JSON）。

任何解析失败都回退到内置合法卡池（mock），保证接口稳定可用。
"""
from __future__ import annotations

import json

from app.llm import LLMGateway
from app.llm.mock import VALIDATE_CARDS
from app.schemas import Card

_DIRECTION_SYSTEM = """你是一款互动小说系统里的「命运卡生成器」。
根据给定的故事设定与上一段剧情，生成 3~5 张候选"命运卡"，每张卡代表一个可选的剧情方向。
要求：
- 卡面用简洁、有画面感的中文（勿写表格/Markdown）
- 覆盖不同方向：EVENT 随机事件 / ACTION 角色行动 / SCENE 场景转移 / MEETING 遇见新角色 / FORESHADOW 伏笔
- 稀有度 N|R|SR|SSR；SSR 卡必须含 risk_balance（张力 + 后续转折建议），且剧情张力明显更高
- weight(1~100) 表示相对出现概率
- 严格只输出一个 JSON 数组，不要任何额外文字。
数组元素字段：
card_id(string,唯一) title(string≤40) content(string≤200)
label(EVENT|ACTION|SCENE|MEETING|FORESHADOW) rarity(N|R|SR|SSR) weight(int 1~100)
risk_balance(object, 仅SSR必填: {tension:int 1~10, suggested_turn:string≤80})
"""


def _parse_cards(raw: str) -> list[Card]:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("cards", [])
    cards = [Card.model_validate(obj) for obj in data]
    return cards


class DirectionGenerator:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def generate(self, *, premise: str, synopsis: str, tail: str, decision_no: int) -> list[Card]:
        user = (
            f"【故事前提】{premise}\n"
            f"【故事简介】{synopsis}\n"
            f"【待决剧情尾巴】{tail}\n"
            f"【本次分歧节点 #{decision_no}】请输出命运卡 JSON 数组："
        )
        try:
            raw = await self._gateway.complete(task="direction", system=_DIRECTION_SYSTEM, user=user)
            cards = _parse_cards(raw)
            if not (3 <= len(cards) <= 5) or len({c.card_id for c in cards}) != len(cards):
                raise ValueError(f"卡池数量/唯一性不合法: {len(cards)}")
            return cards
        except Exception:  # 解析失败或上游出错 → 回退内置合法卡池
            return list(VALIDATE_CARDS)