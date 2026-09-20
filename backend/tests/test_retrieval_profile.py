"""检索画像（开书一次判定 + 按画像预取 + 正文时效联网）测试。"""
import anyio

from app.services.grounding import GroundingService
from app.services.retrieval import (
    ProfileDeterminer,
    RetrievalProfile,
    prefetch,
    _keyword_fallback,
)
from app.schemas import DirectionKind, DirectionSpec
from app.services.store import Story
from app.services.story_service import StoryService


class _FakeWeb:
    """可注入 GroundingService 的假联网：记录调用，便于断言正文本是否联网。"""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.calls: list[str] = []

    async def search(self, query: str) -> str | None:
        self.calls.append(query)
        return f"『{query}』的实时摘要"


class TestKeywordFallback:
    def test_coal_mine_premise_is_profiled(self):
        # "山西下井"这类中文职业/地域题材：关键词兜底必须识别为高专业需求并给出煤矿专题
        prof = _keyword_fallback("我在山西下井的日子", "记录井下矿工的真实生活")
        assert prof.real_world == "high"
        assert prof.profession["level"] == "high"
        assert "采掘" in prof.profession["domains"]
        labels = [t["label"] for t in prof.topics]
        assert any("煤矿" in l or "井下" in l for l in labels)
        assert prof.require_web is True

    def test_legitimate_triggering_shared_helper(self):
        prof = _keyword_fallback("法庭", "律师")
        assert prof.profession["level"] == "high"
        assert "法律" in prof.profession["domains"]

    def test_pure_fantasy_gets_no_topics(self):
        prof = _keyword_fallback("少年在雾海的旧城寻找身世", "奇幻架空")
        assert prof.topics == [] and prof.require_web is False

    def test_timeliness_only_for_fresh_reality(self):
        # 稳定职业文不带时效；近未来科技才带
        stable = _keyword_fallback("我在山西下井的日子", "")
        assert stable.timeliness != "high"
        tech = _keyword_fallback("近未来AI公司", "人工智能产品")
        assert tech.timeliness == "high"


class _FakeGateway:
    """返回固定文本的网关桩，模拟一次判定调用。"""

    def __init__(self, text: str) -> None:
        self.text = text

    async def complete(self, *, task, system, user):
        return self.text


class TestProfileDeterminer:
    def test_determine_returns_structured_profile(self):
        gw = _FakeGateway(
            '{"real_world":"high","profession":{"level":"high","domains":["采掘"]},'
            '"timeliness":"low","continuity":"high",'
            '"topics":[{"label":"煤矿井工开采主要流程","kind":"professional"}],"require_web":true}'
        )
        prof = anyio.run(ProfileDeterminer(gw).determine, "我在山西下井的日子", "井下矿工的生活")
        assert prof.real_world == "high"
        assert "采掘" in prof.profession["domains"]
        assert prof.topics[0]["label"] == "煤矿井工开采主要流程"
        assert prof.require_web is True

    def test_llm_failure_falls_back_to_keyword(self):
        class Boom:
            async def complete(self, **kw):
                raise RuntimeError("limit")

        prof = anyio.run(ProfileDeterminer(Boom()).determine, "山西煤矿下井", "")
        assert any("煤矿" in t["label"] or "井下" in t["label"] for t in prof.topics)

    def test_no_gateway_is_defensive(self):
        prof = anyio.run(ProfileDeterminer(None).determine, "随便一句话", "")
        assert isinstance(prof, RetrievalProfile)

    def test_profile_roundtrip_through_merits_dict(self):
        p = RetrievalProfile(
            real_world="high",
            profession={"level": "high", "domains": ["采掘"]},
            timeliness="low", continuity="high",
            topics=[{"label": "煤矿井工开采主要流程", "kind": "professional"}],
            require_web=True,
        )
        clone = RetrievalProfile.from_dict(p.merits_dict())
        assert clone.merits_dict() == p.merits_dict()


class TestPrefetch:
    def test_prefetch_inert_without_web_key(self):
        prof = RetrievalProfile(require_web=True,
                                topics=[{"label": "煤矿井工开采主要流程", "kind": "professional"}])
        web = _FakeWeb(enabled=False)
        facts = anyio.run(prefetch, prof, web)
        assert facts == [] and web.calls == []

    def test_prefetch_gathers_enabled_topics(self):
        prof = RetrievalProfile(require_web=True, topics=[
            {"label": "煤矿井工开采主要流程", "kind": "professional"},
            {"label": "井下安全规程", "kind": "professional"},
        ])
        web = _FakeWeb(enabled=True)
        facts = anyio.run(prefetch, prof, web)
        assert len(facts) == 2
        assert all(f.startswith("专业检索『") for f in facts)

    def test_prefetch_no_topics_is_noop(self):
        prof = RetrievalProfile(require_web=True, topics=[])
        web = _FakeWeb(enabled=True)
        facts = anyio.run(prefetch, prof, web)
        assert facts == []


class TestDecisionTimelinessWeb:
    def _svc(self, web: _FakeWeb) -> StoryService:
        from app.services.vector_kb import build_chroma_facade
        import tempfile
        g = GroundingService(vector=build_chroma_facade(path=tempfile.mkdtemp(), mode="n-gram"),
                             web=web)
        return StoryService(store=None, gateway=None, direction=None, writer=None, grounding=g)

    def test_web_only_when_timeliness_high(self):
        web = _FakeWeb(enabled=True)
        svc = self._svc(web)
        story = Story(id="w", premise="近未来AI公司")
        story.retrieval_profile = {"timeliness": "high", "require_web": True}
        spec = DirectionSpec(kind=DirectionKind.ACTION, summary="开发商一款最新AI产品")
        anyio.run(svc._ground_decision, story, spec)
        assert web.calls, "timeliness=high 且联网可用时应发起一次时效性联网"

    def test_no_web_when_timeliness_not_high(self):
        web = _FakeWeb(enabled=True)
        svc = self._svc(web)
        story = Story(id="c", premise="山城中学")
        story.retrieval_profile = {"timeliness": "low", "require_web": False}
        spec = DirectionSpec(kind=DirectionKind.SCENE, summary="在教室里复习考试")
        anyio.run(svc._ground_decision, story, spec)
        assert web.calls == [], "timeliness!=high 时正文不应发起联网"

    def test_no_web_when_disabled_even_if_timeliness_high(self):
        web = _FakeWeb(enabled=False)  # 未配 key
        svc = self._svc(web)
        story = Story(id="t", premise="最新科技热点")
        story.retrieval_profile = {"timeliness": "high", "require_web": True}
        spec = DirectionSpec(kind=DirectionKind.ACTION, summary="主角关注AI发布会")
        anyio.run(svc._ground_decision, story, spec)
        assert web.calls == []

    def test_old_story_without_profile_is_pure_recall(self):
        web = _FakeWeb(enabled=True)
        svc = self._svc(web)
        story = Story(id="old", premise="近未来商业故事")
        spec = DirectionSpec(kind=DirectionKind.MEETING, summary="去见电商巨头刘强东谈合作")
        added = anyio.run(svc._ground_decision, story, spec)
        assert added and "刘强东" in "".join(story.grounding)
        assert web.calls == []  # 老故事无画像 → 纯知识库召回，不联网


class TestRetrievalProfilePersistence:
    def test_profile_roundtrips_through_snapshot(self):
        from app.storage.sqlite import SQLiteStore

        store = SQLiteStore(":memory:")
        story = Story(id="p", premise="山西煤矿下井")
        story.retrieval_profile = {
            "real_world": "high",
            "profession": {"level": "high", "domains": ["采掘"]},
            "timeliness": "low", "continuity": "low",
            "topics": [{"label": "煤矿井工开采主要流程", "kind": "professional"}],
            "require_web": True,
        }
        store.save(story)
        assert store.get("p").retrieval_profile == story.retrieval_profile
        assert store.snapshot("p")["retrieval_profile"] == story.retrieval_profile