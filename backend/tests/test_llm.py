import pytest

from app.config import Settings
from app.context import current_user_id
from app.llm import LLMGateway
from app.llm.errors import ModelError
from app.schemas import DirectionKind
from app.services.blueprint import BlueprintBuilder
from app.services.direction import DirectionGenerator
from app.services.keychain import Keychain
from app.services.narrative import NarrativeUpdater


def _stub_completer(raw: str):
    class _Stub:
        async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
            return raw

        def stream(self, *args, **kwargs):
            raise AssertionError("unused")

    return _Stub()


def test_gateway_unconfigured_mode():
    # _env_file=None：隔离 ambient backend/.env，确保 api_keys 保持为空
    gw = LLMGateway(Settings(default_provider="deepseek", api_keys={}, _env_file=None))
    assert gw.mode() == "unconfigured"


@pytest.mark.anyio
async def test_gateway_unconfigured_raises():
    """未接入模型时不得静默降级，应明确报错。"""
    gw = LLMGateway(Settings(default_provider="deepseek", api_keys={}, _env_file=None))
    with pytest.raises(ModelError):
        await gw.complete(task="init", system="s", user="u")


def test_gateway_real_mode_when_key_present(tmp_path):
    """公网 BYOK：模型 Key 只来自"当前用户"的 Keychain，不再有全局 env 兜底。"""
    kc = Keychain(str(tmp_path / "kc.db"))
    kc.save(user_id="alice", provider="deepseek", model="deepseek-chat",
            api_key="sk-x", base_url="https://api.deepseek.com/v1")
    gw = LLMGateway(Settings(api_keys={}, _env_file=None), keychain=kc)

    # 未设置当前用户：即使 env 有 key 也不生效（隔离）
    current_user_id.set(None)
    assert gw.mode() == "unconfigured"

    # 命中 alice 的 keychain → 真实模式
    current_user_id.set("alice")
    assert gw.mode() == "openai-compat"
    assert gw.resolve()["api_key"] == "sk-x"


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
           '"relation_updates":[{"a":"阿刻","b":"刻影","label":"仇敌","note":""}],'
           '"new_foreshadows":["新伏笔"]}')
    up = NarrativeUpdater(_stub_completer(raw))
    chars = [{"name": "阿刻", "role": "protagonist"}]
    fs = [{"id": "fs-1", "text": "左肩旧伤", "status": "planted"}]
    rels = [{"a": "阿刻", "b": "刻影", "label": "盟友", "note": ""}]
    nch, nfs, nrel = await up.update(premise="p", synopsis="s", characters=chars,
                                     foreshadows=fs, relations=rels, passage="正文")
    assert nfs[0]["status"] == "paid_off"
    assert len(nfs) == 2 and nfs[1]["text"] == "新伏笔"
    assert nch[0]["moves"] == ["觉悟了"]
    assert nrel[0]["label"] == "仇敌"  # 同一边更新了 label


@pytest.mark.anyio
async def test_narrative_update_lenient_on_bad_output():
    up = NarrativeUpdater(_stub_completer("not-json"))
    chars = [{"name": "阿刻"}]
    fs = [{"id": "f", "text": "t", "status": "planted"}]
    rels = [{"a": "阿刻", "b": "刻影", "label": "宿敌", "note": ""}]
    nch, nfs, nrel = await up.update(premise="p", synopsis="s", characters=chars,
                                     foreshadows=fs, relations=rels, passage="正文")
    assert nch == chars and nfs == fs and nrel == rels


def test_advance_plan_differs_by_concentration():
    up = NarrativeUpdater(None)  # advance_plan 不触网
    # 纯 SCENE 且未触及任何角色/伏笔 → 全账本跳过
    p = up.advance_plan(kind=DirectionKind.SCENE, passage="海边日出",
                        characters=[{"name": "阿刻"}], foreshadows=[{"text": "令牌"}])
    assert not p.any and not p.advance_relations

    # 高浓度 EVENT → 三账本全推进
    p = up.advance_plan(kind=DirectionKind.EVENT, passage="x", characters=[], foreshadows=[])
    assert p.advance_characters and p.advance_foreshadows and p.advance_relations

    # SCENE 但触及角色名 → 只推进关系，不惊动伏笔
    p = up.advance_plan(kind=DirectionKind.SCENE, passage="阿刻走到海边",
                        characters=[{"name": "阿刻"}], foreshadows=[])
    assert p.advance_relations is True
    assert p.advance_foreshadows is False  # 过场不推进伏笔
    assert p.advance_characters is True


@pytest.mark.anyio
async def test_narrative_update_respects_disabled_ledger():
    """advance_foreshadows=False 时即便模型返回伏笔更新也不落账。"""
    raw = ('{"foreshadow_updates":[{"text":"左肩旧伤","status":"paid_off"}],'
           '"relation_updates":[{"a":"甲","b":"乙","label":"同盟","note":""}]}')
    up = NarrativeUpdater(_stub_completer(raw))
    chars = [{"name": "阿刻"}]
    fs = [{"id": "fs-1", "text": "左肩旧伤", "status": "planted"}]
    rels = []
    nch, nfs, nrel = await up.update(premise="p", synopsis="s", characters=chars,
                                     foreshadows=fs, relations=rels, passage="正文",
                                     advance_characters=False, advance_foreshadows=False,
                                     advance_relations=True)
    # 伏笔未被推进、角色未变；关系照常更新（端点按排序归一）
    assert nfs[0]["status"] == "planted"
    assert nch == chars
    assert nrel[0]["a"] == "乙" and nrel[0]["b"] == "甲"
    assert nrel[0]["label"] == "同盟"