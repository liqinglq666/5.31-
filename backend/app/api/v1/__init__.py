from fastapi import APIRouter

from app.api.v1.endpoints import (
    compare,
    status,
    tasks,
    auth,
    admin,
    chat,
    rectification,
    system,
    supplier,
    match,
    memory,
    review,
)

api_router = APIRouter()

api_router.include_router(compare.router, tags=["比对"])
api_router.include_router(status.router, tags=["状态"])
api_router.include_router(tasks.router, tags=["任务管理"])
api_router.include_router(auth.router, tags=["认证"])
api_router.include_router(admin.router, tags=["管理"])
api_router.include_router(chat.router, tags=["对话"])
api_router.include_router(rectification.router, tags=["整改函"])
api_router.include_router(review.router, tags=["审查结果"])
api_router.include_router(system.router, tags=["系统"])
api_router.include_router(supplier.router, tags=["供应商"])
api_router.include_router(match.router, tags=["配对"])
api_router.include_router(memory.router, tags=["记忆层"])
