"""抽卡引擎核心（纯逻辑、不依赖 LLM）。

职责：
- 盲抽（GACHA_DRAW）：按卡 weight 加权随机揭晓一张，稀有度已折算进 weight。
- 提供 rng 注入，便于测试确定性；生产默认零售明文随机（无需预测，随机源由服务端持有）。

注：卡池本身（3~5 张卡的"文案/稀有度/权重"）由 DirectionGenerator(LLM) 生成，本引擎只负责
"从既有卡池抽一张"与校验，与生成解耦，符合《接口契约》§3。
"""
from __future__ import annotations

import random

from app.schemas import Card, CardPool


class GachaEngine:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def draw(self, pool: CardPool) -> Card:
        """盲抽：按 weight 加权随机揭晓一张卡（权重就地归一化）。"""
        if not pool.cards:
            raise ValueError("卡池为空，无法抽取")
        weights = [c.weight for c in pool.cards]
        return self._rng.choices(pool.cards, weights=weights, k=1)[0]

    def pick(self, pool: CardPool, card_id: str) -> Card:
        """明选：从卡池中取指定卡；卡不存在抛 KeyError。"""
        card = pool.by_id(card_id)
        if card is None:
            raise KeyError(f"卡池中不存在 card_id={card_id!r}（pool_version={pool.pool_version}）")
        return card