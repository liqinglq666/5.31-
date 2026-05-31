from typing import List, Dict, Any
from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    task_id: str = Field(..., description="当前比对任务的 ID")
    message: str = Field(..., description="用户当前提问")
    history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description='历史对话记录，格式如 [{"role": "user", "content": "..."}, ...]',
    )
    model_id: str | None = Field(default=None, description="指定 LLM 模型 ID，为空则使用系统默认模型")
    search: bool = Field(default=False, description="是否启用联网搜索")


class GeneralChatRequest(BaseModel):
    """通用聊天请求（无需任务上下文）"""

    message: str = Field(..., description="用户当前提问")
    history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="历史对话记录",
    )
    page_id: str = Field(default="dashboard", description="当前页面标识")
    model_id: str | None = Field(default=None, description="指定 LLM 模型 ID，为空则使用系统默认模型")
    search: bool = Field(default=False, description="是否启用联网搜索")
