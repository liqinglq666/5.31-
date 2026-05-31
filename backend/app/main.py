"""
main.py
-------
FastAPI 应用主入口，精简为只负责：
1. 应用实例化
2. 中间件注册（CORS / 日志）
3. 路由挂载
4. lifespan 初始化数据库
5. 全局异常处理器（统一响应格式）
"""

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, DBAPIError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import init_db
from app.core.exceptions import BankAIError
from app.api.v1 import api_router

# 确保所有 ORM 模型注册到 Base.metadata（包括 memory 模块的新表）
from app.models import memory  # noqa: F401
from app.infrastructure.llm.dynamic_config import refresh_model_config_cache

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Lifespan：应用启动时初始化数据库 + 预热重型模型
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # 刷新大模型动态配置缓存（从数据库加载到内存）
    uvicorn_logger = logging.getLogger("uvicorn")
    try:
        await refresh_model_config_cache()
        uvicorn_logger.info("[Lifespan] 大模型动态配置缓存已刷新")
    except Exception as exc:
        uvicorn_logger.warning("[Lifespan] 大模型配置缓存刷新失败（首次请求前会再次尝试）: %s", exc)

    # 预热 Docling 视觉模型：日志在主线程输出，加载在线程执行
    uvicorn_logger.info("[Lifespan] 开始预热 Docling 视觉模型...")

    def _sync_prewarm() -> str:
        try:
            from app.infrastructure.parser.docling import _get_thread_local_converter
            _get_thread_local_converter()  # 触发懒加载
            return "ok"
        except Exception as exc:
            return str(exc)

    prewarm_result = await asyncio.to_thread(_sync_prewarm)
    if prewarm_result == "ok":
        uvicorn_logger.info("[Lifespan] Docling 模型预热完成")
    else:
        uvicorn_logger.warning(
            "[Lifespan] Docling 预热失败（首次请求时会再次尝试）: %s", prewarm_result
        )
    yield


# ---------------------------------------------------------------------------
# 2. FastAPI 应用实例化
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Bank AI System Backend",
    description="银行内网智能比对系统后端",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# 3. 中间件注册
# ---------------------------------------------------------------------------
class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            logger.error("[Request Error] %s %s: %s", request.method, request.url.path, exc)
            traceback.print_exc()
            raise


app.add_middleware(LogMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://thomas-reasonable-agent-cordless.trycloudflare.com",
        "https://ai.ybl666.xyz",
        "https://www.ybl666.xyz",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ---------------------------------------------------------------------------
# 4. 全局异常处理器（统一响应格式：{code, message, data}）
# ---------------------------------------------------------------------------
_ALLOWED_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}


def _cors_headers(request: Request) -> dict:
    origin = request.headers.get("origin")
    if origin in _ALLOWED_ORIGINS:
        return {"Access-Control-Allow-Origin": origin}
    return {}


def _make_error_response(request: Request, message: str, code: int = 500, status_code: int = 500) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "data": None},
        headers=_cors_headers(request),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """请求参数校验失败（如缺少必填字段、类型不匹配）。"""
    message = "请求参数错误"
    if exc.errors():
        first = exc.errors()[0]
        loc = " ".join(str(x) for x in first.get("loc", []))
        msg = first.get("msg", "")
        message = f"{loc}: {msg}" if loc else msg
    return _make_error_response(request, message, code=422, status_code=422)


@app.exception_handler(BankAIError)
async def bankai_error_handler(request: Request, exc: BankAIError) -> JSONResponse:
    """捕获所有自定义业务异常，直接序列化。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
        headers=_cors_headers(request),
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """数据库唯一约束/外键冲突等 Integrity 异常。"""
    return _make_error_response(request, "数据冲突：该记录已存在或关联数据不完整，请检查后重试。", code=409, status_code=409)


@app.exception_handler(OperationalError)
async def operational_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
    """数据库连接中断、锁超时等 Operational 异常。"""
    return _make_error_response(request, "数据库服务暂时不可用，请稍后重试。", code=503, status_code=503)


@app.exception_handler(DBAPIError)
async def dbapi_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    """其他底层数据库驱动异常。"""
    return _make_error_response(request, "数据库操作失败，请联系管理员。", code=500, status_code=500)


@app.exception_handler(asyncio.TimeoutError)
async def timeout_error_handler(request: Request, exc: asyncio.TimeoutError) -> JSONResponse:
    """AI 引擎调用或外部服务超时。"""
    return _make_error_response(request, "AI 引擎响应超时，请稍后重试或降低任务复杂度。", code=504, status_code=504)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底：捕获所有未处理的异常，避免堆栈泄露到客户端。"""
    traceback.print_exc()
    return _make_error_response(request, "服务器内部错误，请联系管理员。", code=500, status_code=500)


# ---------------------------------------------------------------------------
# 5. 路由挂载
# ---------------------------------------------------------------------------
app.include_router(api_router)


# ---------------------------------------------------------------------------
# 6. 健康检查 / 根路由
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict:
    return {"message": "Bank AI System Backend is running"}
