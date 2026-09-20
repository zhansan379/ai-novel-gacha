"""v1 业务路由：故事 → 卡池 → 盲抽/明选/自由输入 → 生成正文 的决策闭环。"""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.gacha import GachaEngine
from app.llm.errors import LLMError
from app.schemas import Card, CardLabel, CardPool, ChapterInfo, DirectionKind, DirectionSpec
from app.services import registry
from app.services.story_service import chapter_to_info
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


class CreateTaskAccepted(BaseModel):
    task_id: str
    status: str = "pending"


class CreateTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    stage: str | None = None
    result: dict | None = None      # 终态 done 时携带 StoryCreated 同形态数据
    error: dict | None = None       # 终态 error 时携带 {code, message}


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
    next_decision_no: int | None = None
    # 完结/分章信息：story_end 表示该书已完结（不再有下一轮卡池）；
    # chapter 为非空时表示本拍刚收束的章（含 LLM 生成的标题）。
    story_end: bool = False
    chapter: ChapterInfo | None = None


class ApplyResponse(BaseModel):
    decision_no: int
    mode: Literal["gacha_pick", "free"]
    direction_spec: DirectionSpec
    passage: str
    lint: list[dict] = []
    consistency: dict = {"passed": True, "issues": []}
    next_decision_no: int | None = None
    story_end: bool = False
    chapter: ChapterInfo | None = None


class ChaptersResponse(BaseModel):
    story_id: str
    chapters: list[ChapterInfo]
    status: Literal["active", "completed"]


class ChapterRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=60)


class StorySummary(BaseModel):
    story_id: str
    premise: str
    synopsis: str
    passages: list[str]
    next_decision_no: int
    style_profile_id: str = "restrained"
    timeline: list[dict] = []
    chapters: list[ChapterInfo] = []
    status: Literal["active", "completed"] = "active"


class StoryListItem(BaseModel):
    story_id: str
    premise: str
    synopsis: str
    next_decision_no: int
    status: Literal["active", "completed"] = "active"


class StoryList(BaseModel):
    stories: list[StoryListItem]


class ImportStoryBody(BaseModel):
    snapshot: dict


class StyleCompareRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    style_ids: list[str] | None = None


# ---------- 工具 ----------
def _card_spec(card: Card) -> DirectionSpec:
    return DirectionSpec(
        kind=_LABEL_TO_KIND[card.label], summary=card.content,
        constraints=['保持既定文风'], risk_flag=(card.rarity.value == "SSR"),
        cause=card.cause, aftermath=card.aftermath, suspense=card.suspense,
        risk_balance=card.risk_balance,
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


def _ensure_active(story: Story) -> None:
    """故事已完结时拒绝一切新决策（409）。"""
    if story.status == "completed":
        raise HTTPException(status_code=409, detail={"code": "STORY_ENDED",
                                                     "message": "故事已完结，无法继续续写"})


def _sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------- 端点 ----------
@router.post("/stories", status_code=202, response_model=CreateTaskAccepted, tags=["story"])
async def create_story(body: CreateStoryRequest):
    """开书：提交即为后台异步任务，立即返回 task_id（penging）。

    完成后经 GET /v1/stories/tasks/{task_id} 轮询取 StoryCreated 结果；前端据此跳转。
    详情见 app/services/tasks.py。
    """
    def job(on_stage):
        return registry.story_service.create(
            body.premise, style_profile_id=body.style_profile_id, on_stage=on_stage)
    task_id = registry.tasks.submit(job, premise=body.premise)
    return CreateTaskAccepted(task_id=task_id, status="pending")


@router.get("/stories/tasks/{task_id}", response_model=CreateTaskStatusResponse, tags=["story"])
async def get_create_task(task_id: str):
    """查询异步开书任务状态：status=pending/running/done/error；done 带 result，error 带 error。"""
    t = registry.tasks.get(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND",
                                                     "message": "开书任务不存在或已过期（服务可能重启）"})
    return CreateTaskStatusResponse(task_id=t.task_id, status=t.status.value,
                                    stage=t.stage, result=t.result, error=t.error)


@router.get("/stories", response_model=StoryList, tags=["story"])
async def list_stories():
    return StoryList(stories=[StoryListItem(**item) for item in registry.story_service.list()])


@router.post("/stories/import", status_code=201, tags=["story"])
async def import_story(body: ImportStoryBody):
    if not body.snapshot.get("premise"):
        raise HTTPException(status_code=422, detail={"code": "BAD_SNAPSHOT", "message": "快照缺少 premise"})
    story = registry.story_service.import_snapshot(body.snapshot)
    return {"story_id": story.id, "premise": story.premise, "synopsis": story.synopsis}


@router.get("/stories/{sid}/export", tags=["story"])
async def export_story(sid: str = Path(...)):
    decision_path(sid)  # 不存在则 404
    return registry.story_service.export_snapshot(sid)


@router.delete("/stories/{sid}", status_code=204, tags=["story"])
async def delete_story(sid: str = Path(...)):
    if not registry.story_service.delete(sid):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "故事不存在"})
    return Response(status_code=204)


@router.get("/styles", tags=["story"])
async def list_styles():
    from app.services.styles import list_styles as _list
    return {"styles": _list()}


@router.post("/styles/compare", tags=["style"])
async def compare_styles(body: StyleCompareRequest):
    """同一段素材，用若干文风各自改写生成，便于对比（真实调用 LLM）。"""
    from app.services.styles import STYLE_PROFILES, get_style

    ids = body.style_ids if body.style_ids else list(STYLE_PROFILES)
    ids = [sid for sid in ids if sid in STYLE_PROFILES]

    async def _run(sid: str) -> dict:
        style = get_style(sid)
        try:
            output = await registry._writer.compare(body.text, style)  # noqa: SLF001
            return {"style_id": sid, "name": style.name, "output": output, "error": None}
        except LLMError as exc:
            return {"style_id": sid, "name": style.name, "output": None,
                    "error": "".join(str(exc).splitlines())[:200]}

    results = await asyncio.gather(*[_run(sid) for sid in ids])
    return {"results": results}


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
                        timeline=story.timeline,
                        chapters=[ChapterInfo(**chapter_to_info(c)) for c in story.chapters],
                        status=story.status)


@router.get("/stories/{sid}/chapters", response_model=ChaptersResponse, tags=["chapter"])
async def list_chapters(sid: str = Path(...)):
    """章节目录：连同故事状态一起返回（前端目录/完结态用它）。"""
    story = decision_path(sid)
    return ChaptersResponse(story_id=story.id,
                            chapters=[ChapterInfo(**chapter_to_info(c)) for c in story.chapters],
                            status=story.status)


@router.patch("/stories/{sid}/chapters/{no}", response_model=ChapterInfo, tags=["chapter"])
async def rename_chapter(sid: str, no: int, body: ChapterRenameRequest):
    """修改章节标题（读者可改）。"""
    story = decision_path(sid)
    try:
        return ChapterInfo(**(await registry.story_service.rename_chapter(story, no, body.title)))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": str(exc)}) from exc


@router.post("/stories/{sid}/undo", tags=["story"])
async def undo_last_step(sid: str = Path(...)):
    """撤销上一步：回退最后一段正文/时间线，解锁该决策并还原角色与伏笔快照。"""
    story = decision_path(sid)
    try:
        return await registry.story_service.undo_last(story)
    except ValueError as exc:
        raise HTTPException(status_code=409,
                            detail={"code": "NOT_UNDOABLE", "message": str(exc)}) from exc


@router.get("/stories/{sid}/timeline", tags=["story"])
async def get_timeline(sid: str = Path(...)):
    """剧情时间线（复盘账本）：逐决策追加的事件流；区别于世界历史线 world.history。"""
    story = decision_path(sid)
    return {"story_id": story.id, "timeline": story.timeline}


@router.get("/stories/{sid}/blueprint", tags=["story"])
async def get_blueprint(sid: str = Path(...)):
    """读取前置构建：世界观 / 历史线 / 角色 / 卷·章大纲。

    真实事实基座（grounding）与世界历史线做读时相关性过滤：只呈现书里点过名的
    真实实体相关内容，剔除此前误注入的无关史实（如纯架空书历史线里混入的
    真实企业家事记）。
    """
    story = decision_path(sid)
    from app.services.grounding import filter_grounding, filter_real_entity_history
    storyline = f"{story.premise}\n{story.synopsis}"
    return {
        "story_id": story.id,
        "world": story.world,
        "history": filter_real_entity_history(storyline, story.history),
        "characters": story.characters,
        "style": story.style_profile_id,
        "foreshadows": story.foreshadows,
        "relations": story.relations,
        "grounding": filter_grounding(storyline, story.grounding),
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
    # 卡池惰性生成（带当前叙事上下文/上拍悬念），幂等；不在正文流里预生成下一卡池
    cards = await registry.story_service.ensure_cards(story, no)
    return CardsResponse(decision_no=no, pool_version=d.pool_version, cards=cards)


@router.post("/stories/{sid}/decisions/{no}/gacha", response_model=DrawResponse, tags=["decision"])
async def blind_draw(sid: str, no: int = Path(..., ge=1)):
    story = decision_path(sid)
    _ensure_active(story)
    d = _decision_of(story, no)
    if d.applied:
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策的正文已生成，请勿重复提交"})
    d.cards = await registry.story_service.ensure_cards(story, no)
    if not d.cards:
        raise HTTPException(status_code=409, detail={"code": "STORY_ENDED", "message": "故事已完结，无法生成卡池"})
    card = _gacha.draw(CardPool(decision_no=no, pool_version=d.pool_version, cards=d.cards))
    direction = _card_spec(card)
    try:
        passage = await registry.story_service.apply_decision(
            story, no, mode="gacha_draw", direction_spec=direction, card_id=card.card_id,
        )
    except DecisionLocked:
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策的正文已生成，请勿重复提交"})
    chap = ChapterInfo(**passage["chapter"]) if passage.get("chapter") else None
    return DrawResponse(decision_no=no, mode="gacha_draw", card=card,
                        direction_spec=direction,
                        passage=passage["content"], lint=passage.get("lint", []),
                        consistency=passage.get("consistency", {"passed": True, "issues": []}),
                        next_decision_no=story.next_decision_no,
                        story_end=bool(passage.get("story_end")), chapter=chap)


@router.post("/stories/{sid}/decisions/{no}/apply", response_model=ApplyResponse, tags=["decision"])
async def apply_decision(sid: str, no: int, body: AppliesDecision):
    story = decision_path(sid)
    _ensure_active(story)
    d = _decision_of(story, no)
    if d.applied:
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策的正文已生成，请勿重复提交"})
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
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策的正文已生成，请勿重复提交"})
    chap = ChapterInfo(**passage["chapter"]) if passage.get("chapter") else None
    return ApplyResponse(decision_no=no, mode=mode, direction_spec=direction,
                         passage=passage["content"], lint=passage.get("lint", []),
                         consistency=passage.get("consistency", {"passed": True, "issues": []}),
                         next_decision_no=story.next_decision_no,
                         story_end=bool(passage.get("story_end")), chapter=chap)


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

    事件流：passage_start → delta* → passage_end{passage, lint, consistency,
    next_decision_no, story_end, chapter}。story_end=true 表示本书已完结（不再有下一轮卡池）。
    """
    story = decision_path(sid)
    _ensure_active(story)

    card: Card | None = None
    # 解析三选一动作 → (direction_spec, mode, card_id)
    if body.draw:
        d = _decision_of(story, no)
        if d.applied:
            raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策的正文已生成，请勿重复提交"})
        d.cards = await registry.story_service.ensure_cards(story, no)
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
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "该决策的正文已生成，请勿重复提交"})

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
            elif etype == "error":
                yield _sse("passage_error", {"message": ev.get("message", "生成失败，该步已回滚，可重试")})
            else:  # end
                p = ev["passage"]
                chap = ChapterInfo(**p["chapter"]) if p.get("chapter") else None
                yield _sse("passage_end", {
                    "decision_no": no, "passage": p["content"],
                    "lint": p.get("lint", []),
                    "consistency": p.get("consistency", {"passed": True, "issues": []}),
                    "next_decision_no": ev["next_decision_no"],
                    "story_end": bool(ev.get("story_end")),
                    "chapter": chap.model_dump() if chap else None,
                })

    return StreamingResponse(event_stream(), media_type="text/event-stream")