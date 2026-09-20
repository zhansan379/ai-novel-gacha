import json

import pytest

from app.config import Settings
from app.llm import LLMGateway
from app.llm.mock import MOCK_DIRECTION_CARDS, VALIDATE_CARDS
from app.schemas import Card, CardPool


def test_gateway_mock_when_no_key():
    gw = LLMGateway(Settings(default_provider="deepseek", api_keys={}))
    assert gw.mode() == "mock"


def test_gateway_real_mode_when_key_present():
    gw = LLMGateway(Settings(default_provider="deepseek", api_keys={"deepseek": "sk-x"}))
    assert gw.mode() == "openai-compat"


@pytest.mark.anyio
async def test_mock_direction_returns_valid_cards():
    gw = LLMGateway(Settings(api_keys={}))
    raw = await gw.complete(task="direction", system="s", user="u")
    data = json.loads(raw)
    cards = [Card.model_validate(c) for c in data]
    assert 3 <= len(cards) <= 5
    for c in cards:
        if c.rarity.value == "SSR":
            assert c.risk_balance is not None
    assert cards == [Card.model_validate(c) for c in MOCK_DIRECTION_CARDS]


@pytest.mark.anyio
async def test_mock_draft_returns_text():
    gw = LLMGateway(Settings(api_keys={}))
    text = await gw.complete(task="draft", system="s", user="选择：夜雨敲门")
    assert isinstance(text, str) and len(text) > 20


def test_cardpool_from_validated_cards():
    pool = CardPool(decision_no=1, cards=VALIDATE_CARDS)
    assert 3 <= len(pool.cards) <= 5