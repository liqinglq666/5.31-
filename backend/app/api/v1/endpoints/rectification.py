"""
rectification.py
----------------
整改函生成接口：
- 根据任务风险点生成正式的《合同合规整改告知函》
- 使用 LLM 流式返回

职责：仅负责接收请求、校验权限、调用 Service、返回响应。
所有 prompt 构建与消息组装逻辑已下沉到 services/rectification_service.py。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import User
from app.core.security import get_current_user
from app.core.exceptions import DatabaseError, NotFoundError, PermissionDeniedError
from app.crud.crud_task import get_task_db
from app.services.rectification_service import RectificationService

router = APIRouter()


@router.post("/api/v1/generate-rectification/{task_id}")
async def generate_rectification(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    根据指定比对任务的风险点，流式生成《合同合规整改告知函》。
    返回 text/event-stream 格式的 SSE 流。
    """
    try:
        record = await get_task_db(db, task_id)
    except Exception as exc:
        raise DatabaseError("数据库查询异常", detail=str(exc))

    if record is None:
        raise NotFoundError("未找到指定的任务记录")

    # 权限校验：非管理员只能访问自己的任务
    if record.creator_id != current_user.id and not current_user.is_admin:
        raise PermissionDeniedError("无权访问该任务的整改函生成")

    messages = RectificationService.build_messages(record)

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        RectificationService.stream_response(messages),
        media_type="text/event-stream",
    )
