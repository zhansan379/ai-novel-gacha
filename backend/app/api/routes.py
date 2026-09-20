"""v1 业务路由：故事 → 卡池 → 盲抽/明选/自由输入 → 生成正文 的决策闭环。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field, model_validator

from app.gacha import GachaEngine
from app.schemas import Card, CardLabel, CardPool, DirectionKind, DirectionSpec
from app.services import registry
from app.services.store import DecisionLocked, Story, StoryNotFound

router = APIRouter(prefix="/v1")


@router.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "app": registry.gateway.mode()}

# 全局共享一个 GachaEngine（rng 服务端持有）
_gacha = GachaEngine()

_LABEL_TO_KIND: dict[CardLabel, DirectionKind] = {
    CardLabel.EVENT: DirectionKind.EVENT,
    CardLabel.ACTION: DirectionKind.ACTION,
    CardLabel.SCENE: DirectionKind.SCENE,
    CardLabel.MEETING: DirectionKind.MEETING,
    CardLabel.FORESHADOW: DirectionKind.FORESHADOW,
}


# ---------- 请求/响应模型 ----------
class CreateStoryRequest(BaseModel):
    premise: str = Field(min_length=1, max_length=200)
    style_profile_id: str | None = None


class AppliesDecision(BaseModel):
    card_id: str | None = None
    custom_instruction: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _exactly_one(self) -> "AppliesDecision":
        if (self.card_id is None) == (self.custom_instruction is None):
            raise ValueError("apply 需且仅需 card_id 或 custom_instruction 之一")
        return self


class StoryCreated(BaseModel):
    story_id: str
    synopsis: str
    opening: str
    decision_no: int
    cards: list[Card]
    style_profile_id: str


class CardsResponse(BaseModel):
    decision_no: int
    pool_version: int
    cards: list[Card]


class DrawResponse(BaseModel):
    decision_no: int
    mode: Literal["gacha_draw"]
    card: Card
    direction_spec: DirectionSpec
    passage: str
    lint: list[dict] = []
    consistency: dict = {"passed": True, "issues": []}
    next_decision_no: int


class ApplyResponse(BaseModel):
    decision_no: int
    mode: Literal["gacha_pick", "free"]
    direction_spec: DirectionSpec
    passage: str
    lint: list[dict] = []
    consistency: dict = {"passed": True, "issues": []}
    next_decision_no: int


class StorySummary(BaseModel):
    story_id: str
    premise: str
    synopsis: str
    passages: list[str]
    next_decision_no: int
    style_profile_id: str = "restrained"


# ---------- 工具 ----------
def _card_spec(card: Card) -> DirectionSpec:
    return DirectionSpec(
        kind=_LABEL_TO_KIND[card.label], summary=card.content,
        constraints=['保持既定文风'], risk_flag=(card.rarity.value == "SSR"),
    )


def decision_path(sid: str) -> Story:
    try:
        return registry.story_service.get(sid)
    except StoryNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "故事不存在"}) from exc


def _decision_of(story: Story, no: int) -> object:
    d = story.decisions.get(no)
    if d is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"决策节点不存在: {no}"})
    return d


# ---------- 端点 ----------
@router.post("/stories", response_model=StoryCreated, status_code=201, tags=["story"])
async def create_story(body: CreateStoryRequest):
    story = await registry.story_service.create(body.premise, style_profile_id=body.style_profile_id)
    d = _decision_of(story, 1)
    opening = story.passages[0]["content"]
    return StoryCreated(story_id=story.id, synopsis=story.synopsis, opening=opening,
                        decision_no=d.no, cards=d.cards,
                        style_profile_id=story.style_profile_id)


@router.get("/styles", tags=["story"])
async def list_styles():
    from app.services.styles import list_styles as _list
    return {"styles": _list()}


@router.get("/stories/{sid}", response_model=StorySummary, tags=["story"])
async def get_story(sid: str = Path(...)):
    story = decision_path(sid)
    return StorySummary(story_id=story.id, premise=story.premise, synopsis=story.synopsis,
                        passages=[p["content"] for p in story.passages],
                        next_decision_no=story.next_decision_no,
                        style_profile_id=story.style_profile_id)


@router.get("/stories/{sid}/blueprint", tags=["story"])
async def get_blueprint(sid: str = Path(...)):
    """读取前置构建：世界观 / 历史线 / 角色 / 卷·章大纲。"""
    story = decision_path(sid)
    return {
        "story_id": story.id,
        "world": story.world,
        "history": story.history,
        "characters": story.characters,
        "outline": story.outline,
        "style": story.style_profile_id,
    }


@router.get("/stories/{sid}/decisions/{no}/cards", response_model=CardsResponse, tags=["decision"])
async def get_cards(sid: str, no: int = Path(..., ge=1)):
    story = decision_path(sid)
    d = _decision_of(story, no)
    if not d.cards:  # 该节点卡池尚未生成 → 现场生成
        d.cards = await registry._direction.generate(  # noqa: SLF001
            premise=story.premise, synopsis=story.synopsis,
            tail=(story.passages[-1]["content"] if story.passages else ""), decision_no=no,
        )
        registry.store.save(story)
    return CardsResponse(decision_no=no, pool_version=d.pool_version, cards=d.cards)


@router.post("/stories/{sid}/decisions/{no}/gacha", response_model=DrawResponse, tags=["decision"])
async def blind_draw(sid: str, no: int = Path(..., ge=1)):
    story = decision_path(sid)
    d = _decision_of(story, no)
    if d.applied:
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策已锁定"})
    if not d.cards:
        d.cards = await registry._direction.generate(  # noqa: SLF001
            premise=story.premise, synopsis=story.synopsis,
            tail=(story.passages[-1]["content"] if story.passages else ""), decision_no=no,
        )
    card = _gacha.draw(CardPool(decision_no=no, pool_version=d.pool_version, cards=d.cards))
    direction = _card_spec(card)
    try:
        passage = await registry.story_service.apply_decision(
            story, no, mode="gacha_draw", direction_spec=direction, card_id=card.card_id,
        )
    except DecisionLocked:
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策已锁定"})
    return DrawResponse(decision_no=no, mode="gacha_draw", card=card,
                        direction_spec=direction,
                        passage=passage["content"], lint=passage.get("lint", []),
                        consistency=passage.get("consistency", {"passed": True, "issues": []}),
                        next_decision_no=story.next_decision_no)


@router.post("/stories/{sid}/decisions/{no}/apply", response_model=ApplyResponse, tags=["decision"])
async def apply_decision(sid: str, no: int, body: AppliesDecision):
    story = decision_path(sid)
    d = _decision_of(story, no)
    if d.applied:
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策已锁定"})
    if body.card_id is not None:
        card = next((c for c in d.cards if c.card_id == body.card_id), None)
        if card is None:
            raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR",
                                                         "message": f"卡不在当前卡池: {body.card_id}"})
        direction, mode = _card_spec(card), "gacha_pick"
    else:
        direction, mode = registry.story_service.spec_from_instruction(body.custom_instruction), "free"
    try:
        passage = await registry.story_service.apply_decision(
            story, no, mode=mode, direction_spec=direction, card_id=body.card_id,
        )
    except DecisionLocked:
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策已锁定"})
    return ApplyResponse(decision_no=no, mode=mode, direction_spec=direction,
                         passage=passage["content"], lint=passage.get("lint", []),
                         consistency=passage.get("consistency", {"passed": True, "issues": []}),
                         next_decision_no=story.next_decision_no)


@router.post("/stories/{sid}/passages/{np}/lint", response_model=dict, tags=["quality"])
async def relint_passage(sid: str, np: int):
    """对某段已生成正文重新做去 AI 味 + 一致性质检。"""
    story = decision_path(sid)
    if not (1 <= np <= len(story.passages)):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"段落不存在: {np}"})
    p = story.passages[np - 1]
    return await registry.story_service.review(
        premise=story.premise, synopsis=story.synopsis, content=p["content"],
    )