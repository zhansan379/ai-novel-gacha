"""FastAPI 应用入口：注册路由、中间件、健康检查。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings

app = FastAPI(title=settings.app_name, version=settings.version)

# 开发期允许跨域（前端 dev server 5173；也可经 Vite proxy，双保险）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["system"])
def health() -> dict:
    """进程级健康检查（/v1/health 为业务级，见 api.routes）。"""
    return {"status": "ok"}