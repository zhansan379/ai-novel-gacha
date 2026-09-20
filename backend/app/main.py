"""FastAPI 应用入口：注册路由、健康检查。"""
from fastapi import FastAPI

from app.api.routes import router
from app.config import settings

app = FastAPI(title=settings.app_name, version=settings.version)
app.include_router(router)


@app.get("/health", tags=["system"])
def health() -> dict:
    """进程级健康检查（/v1/health 为业务级，见 api.routes）。"""
    return {"status": "ok"}