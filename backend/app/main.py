"""FastAPI 应用入口：注册路由、中间件、健康检查。"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.llm.errors import LLMError, QuotaError

app = FastAPI(title=settings.app_name, version=settings.version)

# 开发期允许跨域（前端 dev server 5173；也可经 Vite proxy，双保险）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LLMError)
async def _llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    """把模型层错误转成规整 JSON（未配置 → 502；配额/限流 → 429），避免回 500。"""
    status = 429 if isinstance(exc, QuotaError) else 502
    return JSONResponse(
        status_code=status,
        content={"detail": {"code": "LLM_ERROR", "message": str(exc)}},
    )


app.include_router(router)


@app.get("/health", tags=["system"])
def health() -> dict:
    """进程级健康检查（/v1/health 为业务级，见 api.routes）。"""
    return {"status": "ok"}