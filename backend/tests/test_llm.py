import pytest

from app.config import Settings
from app.llm import LLMGateway
from app.llm.errors import ModelError
from app.schemas import DirectionKind
from app.services.blueprint import BlueprintBuilder
from app.services.direction import DirectionGenerator
from app.services.narrative import NarrativeUpdater


def _stub_completer(raw: str):
    class _Stub:
        async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
            return raw

        def stream(self, *args, **kwargs):
            raise AssertionError("unused")

    return _Stub()


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


@pytest.mark.anyio
async def test_narrative_update_applies():
    raw = ('{"foreshadow_updates":[{"text":"左肩旧伤","status":"paid_off"}],'
           '"character_updates":[{"name":"阿刻","note":"觉悟了"}],'
           '"new_foreshadows":["新伏笔"]}')
    up = NarrativeUpdater(_stub_completer(raw))
    chars = [{"name": "阿刻", "role": "protagonist"}]
    fs = [{"id": "fs-1", "text": "左肩旧伤", "status": "planted"}]
    nch, nfs = await up.update(premise="p", synopsis="s", characters=chars,
                               foreshadows=fs, passage="正文")
    assert nfs[0]["status"] == "paid_off"
    assert len(nfs) == 2 and nfs[1]["text"] == "新伏笔"
    assert nch[0]["moves"] == ["觉悟了"]


@pytest.mark.anyio
async def test_narrative_update_lenient_on_bad_output():
    up = NarrativeUpdater(_stub_completer("not-json"))
    chars = [{"name": "阿刻"}]
    fs = [{"id": "f", "text": "t", "status": "planted"}]
    nch, nfs = await up.update(premise="p", synopsis="s", characters=chars,
                               foreshadows=fs, passage="正文")
    assert nch == chars and nfs == fs


def test_narrative_should_run_gate():
    up = NarrativeUpdater(None)  # should_run 不触网
    # 纯 SCENE 且未触及任何角色/伏笔 → 跳过
    assert up.should_run(kind=DirectionKind.SCENE, passage="海边日出",
                         characters=[{"name": "阿刻"}], foreshadows=[{"text": "令牌"}]) is False
    # 非 SCENE → 执行
    assert up.should_run(kind=DirectionKind.EVENT, passage="x", characters=[], foreshadows=[]) is True
    # SCENE 但触角色 → 执行
    assert up.should_run(kind=DirectionKind.SCENE, passage="阿刻走到海边",
                         characters=[{"name": "阿刻"}], foreshadows=[]) is True