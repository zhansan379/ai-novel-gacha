"""v1 业务路由。会话/故事/决策/抽卡等端点后续在此扩展。"""
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/v1")


@router.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.version}