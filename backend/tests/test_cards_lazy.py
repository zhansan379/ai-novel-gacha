"""惰性卡池生成 ensure_cards：幂等、带上下文/上拍悬念、并发不重复生成。"""
import anyio

from app.schemas import Card, DirectionKind, DirectionSpec
from app.services.story_service import StoryService
from app.services.store import Story, StoryStore


def _card(cid: str = "c1") -> Card:
    return Card(card_id=cid, title=f"卡{cid}", label="ACTION", rarity="R", weight=50,
                content="一个行动方向", cause="诱因", aftermath="后果", suspense="悬念")


class _FakeDirection:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate(self, **kw) -> list[Card]:
        self.calls.append(kw)
        return [_card()]


def _svc(direction: _FakeDirection) -> tuple[StoryService, StoryStore, Story]:
    store = StoryStore()
    svc = StoryService(store=store, gateway=None, direction=direction, writer=None,
                       grounding=None, profiler=None)
    story = Story(id="s", premise="p", synopsis="s")
    return svc, store, story


def _story_with_node() -> tuple[StoryService, _FakeDirection, Story]:
    fake = _FakeDirection()
    svc, _store, story = _svc(fake)
    # 节点1已应用并留着悬念；advance 创建下一节点 no=2（卡池待惰性生成）
    spec = DirectionSpec(kind=DirectionKind.CUSTOM, summary="上一拍", suspense="未解开的旧悬念")
    first = story.milestone()  # no=1
    first.applied = True
    first.direction_spec = spec
    story.world = {"rules": ["世界规则A"]}  # 让叙事上下文非空，验证被透传
    story.advance()  # no=2
    return svc, fake, story


def test_ensure_cards_generates_and_is_idempotent():
    svc, fake, story = _story_with_node()
    cards1 = anyio.run(svc.ensure_cards, story, 2)
    assert len(cards1) == 1 and len(fake.calls) == 1
    cards2 = anyio.run(svc.ensure_cards, story, 2)  # 幂等：不再生成
    assert cards2 == cards1 and len(fake.calls) == 1


def test_ensure_cards_passes_context_and_carryover():
    svc, fake, story = _story_with_node()
    anyio.run(svc.ensure_cards, story, 2)
    kw = fake.calls[0]
    assert "世界规则A" in kw.get("context", "")  # 带叙事上下文
    assert "未解开的旧悬念" in kw.get("carryover", "")  # 带上拍悬念


def test_ensure_cards_does_not_regenerate_concurrently():
    svc, fake, story = _story_with_node()

    async def run():
        a, b = await anyio.gather(svc.ensure_cards(story, 2), svc.ensure_cards(story, 2))
        return a, b

    a, b = anyio.run(run)
    assert a == b and len(fake.calls) == 1  # 并发锁：只生成一次