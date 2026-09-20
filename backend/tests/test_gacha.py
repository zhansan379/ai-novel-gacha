import pytest
from pydantic import ValidationError

from app.gacha import GachaEngine
from app.schemas import Card, CardPool, Rarity, RiskBalance


def _card(card_id: str, rarity: Rarity = Rarity.N, weight: int = 50,
          risk: RiskBalance | None = None) -> Card:
    return Card(
        card_id=card_id,
        title=f"卡{card_id}",
        content=f"剧情方向 {card_id}",
        label="EVENT",
        rarity=rarity,
        weight=weight,
        risk_balance=risk,
    )


def _pool(*cards: Card) -> CardPool:
    return CardPool(decision_no=1, cards=list(cards))


def test_ssr_requires_risk_balance():
    with pytest.raises(ValidationError, match="risk_balance"):
        _card("x", Rarity.SSR)


def test_weight_range_enforced():
    with pytest.raises(ValidationError):
        _card("low", weight=0)
    with pytest.raises(ValidationError):
        _card("high", weight=101)


def test_pool_card_count_bounds():
    with pytest.raises(ValidationError):
        CardPool(decision_no=1, cards=[])
    with pytest.raises(ValidationError):
        CardPool(decision_no=1, cards=[_card(str(i)) for i in range(6)])


def test_ssr_with_risk_balance_ok():
    card = _card("ssr", Rarity.SSR, risk=RiskBalance(tension=9, suggested_turn="揭晓身份"))
    assert card.rarity == Rarity.SSR


def test_draw_weights_toward_heavy_card():
    """权重 100 vs 1：连抽 200 次，重卡应显著占优。"""
    heavy = _card("heavy", weight=100)
    light = _card("light", weight=1)
    pool = _pool(heavy, light)
    engine = GachaEngine()
    hits = sum(1 for _ in range(200) if engine.draw(pool).card_id == "heavy")
    assert hits > 150  # 几乎必然占优


def test_single_card_always_drawn():
    pool = _pool(_card("only"))
    engine = GachaEngine()
    assert all(engine.draw(pool).card_id == "only" for _ in range(50))


def test_pick_returns_matching_card():
    pool = _pool(_card("a"), _card("b"))
    assert GachaEngine().pick(pool, "b").card_id == "b"


def test_pick_unknown_card_raises():
    with pytest.raises(KeyError):
        GachaEngine().pick(_pool(_card("a")), "nope")


def test_empty_pool_draw_raises():
    # 空卡池在 schema 层会被拦截，故用 model_construct 绕过校验构造，专门测引擎兜底
    pool = CardPool.model_construct(decision_no=1, pool_version=1, cards=[])
    with pytest.raises(ValueError, match="卡池为空"):
        GachaEngine().draw(pool)


def test_engine_rng_injectable():
    """rng 注入用于测试确定性。"""
    pool = _pool(_card("a", weight=1), _card("b", weight=1))
    eng1 = GachaEngine(rng=__import__("random").Random(42))
    eng2 = GachaEngine(rng=__import__("random").Random(42))
    assert eng1.draw(pool).card_id == eng2.draw(pool).card_id