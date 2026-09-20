"""简介生成的真实信息策略测试：知识库+网络预取合成为简介输入，+事实校验门。

用记录型 stub 网关验证三条关键路径：
- create 在生成简介前完成「知识库召回 + 画像判定 + 网络预取」，并把完整真实上下文注入 init 的 user prompt，
  让全书种子（简介）出生即带事实，而非凭模型记忆虚构。
- 校验门检出 critical 事实冲突时，会带反馈把简介重写一次（story.synopsis_checked 记录 retries）。
- narrative.update / progression.judge 现在也能拿到真实事实（不再缺失事实基座）。

conftest 已把 registry 网络预先置离线，这里直接用注入的 fake web 模拟预取，不发真实请求。
"""
import asyncio
import json
import tempfile

import pytest

from app.config import settings
from app.services.blueprint import BlueprintBuilder
from app.services.direction import DirectionGenerator
from app.services.grounding import GroundingService
from app.services.narrative import NarrativeUpdater
from app.services.progression import ProgressionService
from app.services.retrieval import ProfileDeterminer
from app.services.story_service import StoryService
from app.services.store import Story, StoryStore
from app.services.vector_kb import build_chroma_facade
from app.services.writer import WriterAgent
from app.schemas import DirectionKind, DirectionSpec

_STUB_BLUEPRINT = {
    "world": {"rules": ["商战规则"], "geography": "北京", "power_system": "资本",
              "factions": ["行业协会"], "constraints": ["监管"]},
    "history": [{"era": "当代", "event": "某收购案", "impact": "行业洗牌"}],
    "characters": [{"name": "主角", "role": "protagonist", "goal": "立足",
                    "inner_need": "被认可", "flaw": "冲动", "trait": "敏锐"}],
    "relationships": [],
    "foreshadow_seeds": ["一张旧名片"],
}
_STUB_CARDS = [
    {"card_id": "c1", "title": "变局", "label": "EVENT", "rarity": "R", "weight": 40,
     "content": "总部传来一封密函。", "cause": "有人举报了账目", "aftermath": "主角被约谈",
     "suspense": "密函署名异常"},
    {"card_id": "c2", "title": "故人", "label": "MEETING", "rarity": "SR", "weight": 25,
     "content": "一位旧识找上门来。", "cause": "旧识看到了报道中的主角", "aftermath": "旧识透露了关键往事",
     "suspense": "旧识欲言又止"},
    {"card_id": "c3", "title": "线索", "label": "FORESHADOW", "rarity": "N", "weight": 60,
     "content": "办公桌下压着一封旧信。", "cause": "主角整理办公室时无意发现", "aftermath": "主角开始留意前任的踪迹",
     "suspense": "信的落款是本该去世的人"},
]
_PROFILE_JSON = json.dumps({
    "real_world": "high", "profession": {"level": "high", "domains": ["金融"]},
    "timeliness": "low", "continuity": "low",
    "topics": [{"label": "京东发展与刘强东", "kind": "professional"}],
    "require_web": True,
}, ensure_ascii=False)


class _FakeWeb:
    """模拟可用的联网检索：把画像专题转成一条带来源的事实行，不发真实请求。"""

    enabled = True

    async def search(self, query: str) -> str:
        return "刘强东，京东集团创始人……（联网摘要）"


class _RecGateway:
    """记录型 stub：按 task 回罐装输出，并记下每次 complete 调用，供断言。"""

    def __init__(self):
        self.calls = []
        self.init_replies = [
            "一个当代商战故事：主角是刘强东的助理，在电商巨头的漩涡里找回初心。"
        ]
        self._init_i = 0

    async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
        self.calls.append({"task": task, "system": system, "user": user})
        if task == "init":
            reply = self.init_replies[self._init_i] if self._init_i < len(self.init_replies) \
                else self.init_replies[-1]
            self._init_i += 1
            return reply
        if task == "retrieval-profile":
            return _PROFILE_JSON
        if task == "blueprint":
            return json.dumps(_STUB_BLUEPRINT, ensure_ascii=False)
        if task == "direction":
            return json.dumps(_STUB_CARDS, ensure_ascii=False)
        if task == "consistency":
            return '{"passed": true, "issues": []}'
        if task == "stream":
            raise AssertionError("unused")
        return "正文。"


def _svc(gw, web=None):
    grounding = GroundingService(
        vector=build_chroma_facade(path=tempfile.mkdtemp(), mode="n-gram"), web=web)
    return StoryService(
        store=StoryStore(), gateway=gw,
        direction=DirectionGenerator(gw), writer=WriterAgent(gw),
        grounding=grounding, profiler=ProfileDeterminer(gw),
        progression=ProgressionService(gw),
    )


def test_create_injects_full_context_into_synopsis(monkeypatch):
    monkeypatch.setattr(settings, "book_fanout", False)
    gw = _RecGateway()
    svc = _svc(gw, _FakeWeb())

    story = asyncio.run(svc.create("我是刘强东的助理", style_profile_id="restrained"))

    # 简介 init 调用必须带「知识库 + 网络预取」合成的完整真实上下文
    init_call = [c for c in gw.calls if c["task"] == "init"][0]
    assert "真实事实基座" in init_call["user"]
    assert "刘强东" in init_call["user"]                        # 知识库实体事实
    assert "专业检索『京东发展与刘强东』" in init_call["user"]     # 网络预取事实
    assert story.synopsis.strip()
    # 已落库并暴露校验门结果
    assert story.grounding and any("专业检索" in g for g in story.grounding)
    assert story.synopsis_checked.get("passed") is True


def test_create_without_web_degrades_to_kb_only(monkeypatch):
    monkeypatch.setattr(settings, "book_fanout", False)
    gw = _RecGateway()
    svc = _svc(gw, web=None)  # 未配 web → 仅知识库

    story = asyncio.run(svc.create("我是刘强东的助理", style_profile_id="restrained"))

    init_call = [c for c in gw.calls if c["task"] == "init"][0]
    # 知识库事实仍在（真实实体召回与 web 无关）
    assert "刘强东" in init_call["user"]
    assert "专业检索" not in init_call["user"]  # web 缺失时不预取


def test_verify_synopsis_skips_without_facts(monkeypatch):
    gw = _RecGateway()
    svc = _svc(gw)  # 纯架空前提 → 无真实事实
    story = Story(id="x", premise="少年在雾海旧城寻找失去的身世")

    result = asyncio.run(svc._verify_synopsis(story, full_context=""))

    assert result["checked"] is True and result["passed"] is True
    assert result["note"] == "无真实事实可校验"
    # 没有触发任何一致性调用（无事实直接放行）
    assert not any(c["task"] == "consistency" for c in gw.calls)


def test_verify_synopsis_rewrites_on_critical_conflict(monkeypatch):
    class _ConflictGate:
        def __init__(self):
            self.calls = []
            self.consistency_synopsis_checks = 0

        async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
            self.calls.append({"task": task, "system": system, "user": user})
            if task == "init":
                if "上一稿简介被审出事实冲突" in user:
                    return "已纠正：以真实履历为准，刘强东1998年创办京东，未于2023年辞职。"
                return "旧稿臆断：刘强东2023年已从京东辞职。"
            if task == "retrieval-profile":
                return _PROFILE_JSON
            # 只数「简介事实校验门」本尊，跳过文本质检的一致性
            if task == "consistency" and "事实行审查" in system:
                self.consistency_synopsis_checks += 1
                if self.consistency_synopsis_checks == 1:
                    return ('{"passed": false, "issues": [{"type":"FACT","severity":"critical",'
                            '"fragment":"刘强东2023年已辞职","reason":"刘强东并未于2023年辞职"}]}')
                return '{"passed": true, "issues": []}'
            if task == "blueprint":
                return json.dumps(_STUB_BLUEPRINT, ensure_ascii=False)
            if task == "direction":
                return json.dumps(_STUB_CARDS, ensure_ascii=False)
            return '{"passed": true, "issues": []}'

    gw = _ConflictGate()
    svc = _svc(gw)
    story = Story(id="y", premise="我是刘强东的助理")
    story.grounding = ["• 刘强东：1998年创办京东"]

    result = asyncio.run(svc._verify_synopsis(story, full_context=""))

    assert result["passed"] is True          # 冲突已重写并通过
    assert result["retries"] == 1
    assert "未于2023年辞职" in story.synopsis   # 第二稿采纳了纠正
    assert gw.consistency_synopsis_checks == 2  # 首检(冲突) + 复检(通过)


def test_narrative_update_receives_facts():
    class _Rec:
        def __init__(self):
            self.calls = []

        async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
            self.calls.append(user)
            return json.dumps({"foreshadow_updates": [], "character_updates": [],
                               "relation_updates": [], "new_foreshadows": []})

    gw = _Rec()
    up = NarrativeUpdater(gw)
    chars = [{"name": "主角"}]
    fs = []
    rels = []
    asyncio.run(up.update(premise="p", synopsis="s", characters=chars, foreshadows=fs,
                          relations=rels, passage="正文", facts=["真实事实：刘强东：1998年创办京东"]))
    assert "真实事实（须尊重" in gw.calls[0]
    assert "刘强东：1998年创办京东" in gw.calls[0]


def test_progression_judge_receives_facts():
    class _Rec:
        def __init__(self):
            self.calls = []

        async def complete(self, *, task, system, user, max_tokens=None, temperature=None):
            self.calls.append(user)
            return '{"end_chapter": false, "chapter_title": "", "end_story": false, "reason": "x"}'

    gw = _Rec()
    prog = ProgressionService(gw)
    story = Story(id="z", premise="p")
    spec = DirectionSpec(kind=DirectionKind.EVENT, summary="主角去找刘强东合作")
    verdict = asyncio.run(prog.judge(story, spec, "正文", facts=["真实事实：刘强东：1998年创办京东"]))
    assert "真实事实（须尊重" in gw.calls[0]
    assert "刘强东：1998年创办京东" in gw.calls[0]
    assert verdict["end_chapter"] is False