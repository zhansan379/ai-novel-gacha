"""章节 + 完结：LLM 判定分章、结局收敛、完结态守卫、存储往返、重命名。"""
import anyio
import pytest

from app.schemas import Card, DirectionKind, DirectionSpec
from app.services.progression import ProgressionService
from app.services.story_service import StoryService, chapter_to_info
from app.services.store import Decision, Story
from app.storage.sqlite import SQLiteStore


def _story() -> Story:
    s = Story(id="s1", premise="p", synopsis="s")
    s.open_chapter()  # 第 1 章
    s.passages.append({"no": 1, "decision_no": None, "content": "开篇。"})
    s.open_chapter().passage_to = 1
    return s


class _FakeProgression:
    """可编程的判定桩：按调用顺序弹出预设判定。"""
    def __init__(self, verdicts=None):
        self._verdicts = list(verdicts or [])

    async def judge(self, story, direction_spec, prose):
        if self._verdicts:
            return self._verdicts.pop(0)
        return {"end_chapter": False, "chapter_title": "", "end_story": False, "reason": "noop"}


class _FakeWriter:
    def __init__(self, text="正文段落……"):
        self._text = text

    async def generate(self, **kw):
        return self._text

    async def stream_generate(self, **kw):
        for chunk in (self._text[i:i + 3] for i in range(0, len(self._text), 3)):
            yield chunk


def _svc(tmp_path, progression):
    store = SQLiteStore(str(tmp_path / "test.db"))
    svc = StoryService(store=store, gateway=None, direction=None, writer=_FakeWriter(),
                       grounding=None, profiler=None, progression=progression)
    # 让正文流程只关注分章本身：质检/叙事推进/联网全部短路
    svc._quality = _stub_quality
    svc._advance_state = _stub_async
    svc._ground_decision = _stub_async
    return svc, store


async def _stub_quality(*a, **k):
    return [], {"passed": True, "issues": []}


async def _stub_async(*a, **k):
    return None


def _mk_spec() -> DirectionSpec:
    return DirectionSpec(kind=DirectionKind.ACTION, summary="前进")


def _mk_card() -> Card:
    return Card(card_id="c1", title="卡", label="ACTION", rarity="R", weight=50,
                content="行动", cause="诱因", aftermath="后果", suspense="悬念")


def _mk_decision(no: int) -> Decision:
    d = Decision(no=no, cards=[_mk_card()])
    return d


def test_judge_closes_chapter(tmp_path):
    fake = _FakeProgression([{"end_chapter": True, "chapter_title": "雾海初探",
                              "end_story": False, "reason": "本拍收束"}])
    svc, _store = _svc(tmp_path, progression=fake)
    story = _story()
    story.decisions[1] = _mk_decision(1)

    closed = anyio.run(svc._apply_progression, story, _mk_spec(), "正文段落……")

    assert closed is not None
    assert closed.title == "雾海初探"
    assert closed.status == "closed"
    assert closed.is_final is False
    assert story.open_chapter().no == 2  # 收束后自动开新章
    assert story.status == "active"


def test_judge_failure_never_blocks(tmp_path):
    class Boom:
        async def judge(self, *a, **k):
            raise RuntimeError("模型不可用")
    svc, _store = _svc(tmp_path, progression=Boom())
    story = _story()

    closed = anyio.run(svc._apply_progression, story, _mk_spec(), "正文段落……")

    assert closed is None
    assert len(story.chapters) == 1
    assert story.status == "active"


def test_end_story_marks_completed(tmp_path):
    fake = _FakeProgression([{"end_chapter": True, "chapter_title": "旧城落日",
                              "end_story": True, "reason": "主线已收束"}])
    svc, store = _svc(tmp_path, progression=fake)
    story = _story()
    story.decisions[1] = _mk_decision(1)

    closed = anyio.run(svc._apply_progression, story, _mk_spec(), "正文段落……")

    assert closed.is_final is True
    assert story.status == "completed"
    assert [c.status for c in story.chapters] == ["closed"]  # 结局章不自动开新章

    story.advance()
    assert anyio.run(svc.ensure_cards, story, story.next_decision_no) == []  # 完结后无卡池


def test_apply_decision_end_to_end_story_end(tmp_path):
    fake = _FakeProgression([{"end_chapter": False, "chapter_title": "", "end_story": False, "reason": "x"},
                             {"end_chapter": True, "chapter_title": "尾声", "end_story": True, "reason": "收敛"}])
    svc, _store = _svc(tmp_path, progression=fake)
    story = _story()
    story.decisions[1] = _mk_decision(1)

    p1 = anyio.run(svc.apply_decision, story, 1, "gacha_pick", _mk_spec(), "c1")
    assert p1.get("story_end") is False
    assert p1.get("chapter") is None
    assert story.status == "active"

    story.decisions[2] = _mk_decision(2)
    p2 = anyio.run(svc.apply_decision, story, 2, "gacha_pick", _mk_spec(), "c1")
    assert p2.get("story_end") is True
    assert p2.get("chapter") is not None
    assert p2["chapter"]["is_final"] is True
    assert story.status == "completed"


def test_rename_chapter(tmp_path):
    fake = _FakeProgression([{"end_chapter": True, "chapter_title": "原名", "end_story": False, "reason": "x"}])
    svc, _store = _svc(tmp_path, progression=fake)
    story = _story()
    story.decisions[1] = _mk_decision(1)
    anyio.run(svc._apply_progression, story, _mk_spec(), "x")

    info = anyio.run(svc.rename_chapter, story, 1, "改后的标题")
    assert info["title"] == "改后的标题"
    assert story.chapters[0].title == "改后的标题"
    with pytest.raises(KeyError):
        anyio.run(svc.rename_chapter, story, 99, "不存在")


def test_storage_roundtrip(tmp_path):
    fake = _FakeProgression([{"end_chapter": True, "chapter_title": "第1章标题",
                              "end_story": True, "reason": "完结"}])
    svc, store = _svc(tmp_path, progression=fake)
    story = _story()
    story.decisions[1] = _mk_decision(1)
    anyio.run(svc._apply_progression, story, _mk_spec(), "正文……")

    store.save(story)
    restored = store.get("s1")

    assert restored.status == "completed"
    assert len(restored.chapters) == 1
    assert restored.chapters[0].title == "第1章标题"
    assert restored.chapters[0].is_final is True
    assert chapter_to_info(restored.chapters[0])["status"] == "closed"


def test_progression_service_degrades_on_broken_gateway(tmp_path):
    # gateway=None：complete 会抛错，judge 必须回退为“不收束、不完结”而不抛异常
    svc = ProgressionService(None)
    story = _story()
    verdict = anyio.run(svc.judge, story, _mk_spec(), "正文段落……")
    assert verdict["end_chapter"] is False
    assert verdict["end_story"] is False