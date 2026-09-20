import pytest

from app.config import Settings
from app.llm import LLMGateway
from app.llm.errors import ModelError
from app.services.blueprint import BlueprintBuilder
from app.services.direction import DirectionGenerator


def test_gateway_unconfigured_mode():
    gw = LLMGateway(Settings(default_provider="deepseek", api_keys={}))
    assert gw.mode() == "unconfigured"


@pytest.mark.anyio
async def test_gateway_unconfigured_raises():
    """未接入模型时不得静默降级，应明确报错。"""
    gw = LLMGateway(Settings(default_provider="deepseek", api_keys={}))
    with pytest.raises(ModelError):
        await gw.complete(task="init", system="s", user="u")


def test_gateway_real_mode_when_key_present():
    gw = LLMGateway(Settings(default_provider="deepseek", api_keys={"deepseek": "sk-x"}))
    assert gw.mode() == "openai-compat"


@pytest.mark.anyio
async def test_direction_invalid_output_raises_not_fallback():
    """模型返回无法解析/数量不合法时不再回退内置卡池，而是明确报错。"""

    class StubGateway:
        async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
            return "not-json"

        def stream(self, *args, **kwargs):
            raise AssertionError("unused")

    gen = DirectionGenerator(StubGateway())
    with pytest.raises(ModelError):
        await gen.generate(premise="p", synopsis="s", tail="t", decision_no=1)


@pytest.mark.anyio
async def test_blueprint_invalid_output_raises_not_fallback():
    """蓝图解析失败时不再回退占位，而是明确报错。"""

    class StubGateway:
        async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
            return "not-json"

        def stream(self, *args, **kwargs):
            raise AssertionError("unused")

    builder = BlueprintBuilder(StubGateway())
    with pytest.raises(ModelError):
        await builder.build(premise="p", synopsis="s")