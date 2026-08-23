"""
chat.py
-------
AI 助手流式问答接口：
- 基于任务比对结果进行文档问答
- 使用原生 openai.AsyncOpenAI + SSE 流式响应

职责：仅负责接收请求、校验权限、调用 Service、返回响应。
所有 prompt 构建与消息组装逻辑已下沉到 services/chat_service.py。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import User
from app.core.security import get_current_user, get_current_user_or_guest
from app.core.exceptions import DatabaseError, NotFoundError, PermissionDeniedError
from app.crud.crud_task import get_task_db
from app.schemas.chat import ChatMessageRequest, GeneralChatRequest
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("/api/v1/chat/general")
async def chat_general(
    request: GeneralChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_guest),
):
    """
    通用流式聊天接口（无需任务上下文）。
    返回 text/event-stream 格式的 SSE 流。
    """
    chat_service = ChatService(db)
    context = await chat_service.build_general_context(request.page_id)
    messages = chat_service.build_general_chat_messages(request, context)

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        chat_service.stream_response(
            messages,
            request.model_id,
            search=request.search,
            user_message=request.message,
        ),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


@router.post("/api/v1/chat/document")
async def chat_document(
    request: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    基于指定比对任务的上下文，进行流式文档问答。
    返回 text/event-stream 格式的 SSE 流。
    """
    try:
        record = await get_task_db(db, request.task_id)
    except Exception as exc:
        raise DatabaseError("数据库查询异常", detail=str(exc))

    if record is None:
        raise NotFoundError("未找到指定的任务记录")

    # 权限校验：非管理员只能访问自己的任务
    if record.creator_id != current_user.id and not current_user.is_admin:
        raise PermissionDeniedError("无权访问该任务的对话上下文")

    messages = ChatService.build_document_chat_messages(request, record)

    chat_service = ChatService(db)
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        chat_service.stream_response(
            messages,
            request.model_id,
            search=request.search,
            user_message=request.message,
        ),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
