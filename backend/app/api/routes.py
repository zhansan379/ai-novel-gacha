"""v1 业务路由：故事 → 卡池 → 盲抽/明选/自由输入 → 生成正文 的决策闭环。"""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import StreamingResponse
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


class StreamDecision(BaseModel):
    draw: bool = False
    card_id: str | None = None
    custom_instruction: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _exactly_one_action(self) -> "StreamDecision":
        chosen = [self.draw, self.card_id is not None, self.custom_instruction is not None]
        if sum(chosen) != 1:
            raise ValueError("stream 需且仅需 draw / card_id / custom_instruction 之一")
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
    timeline: list[dict] = []


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


def _sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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


# ---------- 模型接入配置（前端可设） ----------
class ModelConfigRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=80)
    base_url: str = Field(default="", max_length=200)
    api_key: str = Field(default="", max_length=300)


@router.get("/models/config", tags=["config"])
def get_model_config():
    """读取当前模型接入状态（Key 脱敏，仅返回是否已设置）。"""
    from app.services.keychain import default_base_url
    cfg = registry.gateway.resolve()
    provider = cfg["provider"] if cfg else registry.gateway.settings.default_provider
    base = cfg["base_url"] if cfg else default_base_url(provider)
    return {
        "provider": provider,
        "model": (cfg or {}).get("model", ""),
        "base_url": base,
        "configured": cfg is not None,
        "api_key_set": bool(cfg and cfg.get("api_key")),
        "mode": registry.gateway.mode(),
    }


@router.post("/models/config", tags=["config"])
async def set_model_config(body: ModelConfigRequest):
    """保存模型接入配置（持久化到 SQLite；Key 不回传明文）。"""
    from app.services.keychain import default_base_url
    base_url = body.base_url.strip() or default_base_url(body.provider.strip())
    registry.keychain.save(provider=body.provider.strip(), model=body.model.strip(),
                           base_url=base_url, api_key=body.api_key.strip())
    cfg = registry.gateway.resolve()
    return {
        "provider": cfg["provider"], "model": cfg["model"], "base_url": cfg["base_url"],
        "configured": True, "api_key_set": bool(cfg.get("api_key")),
        "mode": registry.gateway.mode(),
    }


@router.post("/models/config/clear", tags=["config"])
async def clear_model_config():
    """清空前端配置；此后未再配置时将报错提示接入模型。"""
    registry.keychain.clear()
    return {"configured": False, "mode": registry.gateway.mode()}


@router.get("/stories/{sid}", response_model=StorySummary, tags=["story"])
async def get_story(sid: str = Path(...)):
    story = decision_path(sid)
    return StorySummary(story_id=story.id, premise=story.premise, synopsis=story.synopsis,
                        passages=[p["content"] for p in story.passages],
                        next_decision_no=story.next_decision_no,
                        style_profile_id=story.style_profile_id,
                        timeline=story.timeline)


@router.get("/stories/{sid}/timeline", tags=["story"])
async def get_timeline(sid: str = Path(...)):
    """剧情时间线（复盘账本）：逐决策追加的事件流；区别于世界历史线 world.history。"""
    story = decision_path(sid)
    return {"story_id": story.id, "timeline": story.timeline}


@router.get("/stories/{sid}/blueprint", tags=["story"])
async def get_blueprint(sid: str = Path(...)):
    """读取前置构建：世界观 / 历史线 / 角色 / 卷·章大纲。"""
    story = decision_path(sid)
    return {
        "story_id": story.id,
        "world": story.world,
        "history": story.history,
        "characters": story.characters,
        "style": story.style_profile_id,
        "foreshadows": story.foreshadows,
    }


@router.get("/stories/{sid}/foreshadows", tags=["story"])
async def get_foreshadows(sid: str = Path(...)):
    """伏笔账本：已埋设 / 推进中 / 已兑现。"""
    story = decision_path(sid)
    return {"story_id": story.id, "foreshadows": story.foreshadows}


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
    from app.services.facts import build_facts
    return await registry.story_service.review(
        premise=story.premise, synopsis=story.synopsis, content=p["content"], facts=build_facts(story),
    )


@router.post("/stories/{sid}/decisions/{no}/stream", tags=["decision"])
async def stream_decision(sid: str, no: int, body: StreamDecision):
    """SSE 流式：按 盲抽/明选/自由输入 之一锁定决策并流式生成正文。

    事件流：passage_start → delta* → passage_end{passage, lint, consistency, next_decision_no}
    """
    story = decision_path(sid)

    card: Card | None = None
    # 解析三选一动作 → (direction_spec, mode, card_id)
    if body.draw:
        d = _decision_of(story, no)
        if d.applied:
            raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策已锁定"})
        if not d.cards:
            d.cards = await registry._direction.generate(  # noqa: SLF001
                premise=story.premise, synopsis=story.synopsis,
                tail=(story.passages[-1]["content"] if story.passages else ""), decision_no=no,
            )
        card = _gacha.draw(CardPool(decision_no=no, pool_version=d.pool_version, cards=d.cards))
        direction, mode, card_id = _card_spec(card), "gacha_draw", card.card_id
    elif body.card_id is not None:
        d = _decision_of(story, no)
        card = next((c for c in d.cards if c.card_id == body.card_id), None)
        if card is None:
            raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR",
                                                         "message": f"卡不在当前卡池: {body.card_id}"})
        direction, mode, card_id = _card_spec(card), "gacha_pick", card.card_id
    else:
        direction = registry.story_service.spec_from_instruction(body.custom_instruction)
        mode, card_id = "free", None

    try:
        gen = registry.story_service.apply_decision_stream(story, no, mode, direction, card_id)
    except DecisionLocked:
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策已锁定"})

    async def event_stream():
        async for ev in gen:
            etype = ev["type"]
            if etype == "start":
                yield _sse("passage_start", {
                    "decision_no": no, "mode": mode, "card_id": card_id,
                    "card": card.model_dump(mode="json") if card else None,
                })
            elif etype == "delta":
                yield _sse("delta", {"text": ev["text"]})
            else:  # end
                p = ev["passage"]
                yield _sse("passage_end", {
                    "decision_no": no, "passage": p["content"],
                    "lint": p.get("lint", []),
                    "consistency": p.get("consistency", {"passed": True, "issues": []}),
                    "next_decision_no": ev["next_decision_no"],
                })

    return StreamingResponse(event_stream(), media_type="text/event-stream")