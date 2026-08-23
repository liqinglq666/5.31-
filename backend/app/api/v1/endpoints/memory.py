"""
api/v1/endpoints/memory.py
--------------------------
拓扑记忆层 RAG 检索接口。

提供基于 Milvus 向量数据库的语义检索能力，支持：
- 跨文档全局检索（不指定 doc_id）
- 单文档内检索（指定 doc_id）
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.exceptions import BankAIError, DatabaseError
from app.models.models import User
from app.infrastructure.vectorstore.milvus import TopoMemoryManager

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="检索查询文本")
    doc_id: Optional[str] = Field(default=None, description="可选：限制在指定文档内检索")
    top_k: int = Field(default=5, ge=1, le=20, description="返回结果数量上限")


class SearchResponseItem(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    level_1: str
    level_2: str
    is_summary: bool
    distance: float


@router.post("/api/v1/memory/search")
async def search_memory(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
):
    """
    基于向量相似度的语义检索接口。
    将查询文本编码为 Embedding 向量，在 Milvus 中检索最相似的语义块。
    """
    try:
        manager = TopoMemoryManager()
        hits = await manager.search_similar(
            query_text=request.query,
            top_k=request.top_k,
            doc_id=request.doc_id,
        )
    except ImportError as exc:
        raise BankAIError(
            f"依赖未安装: {exc}。请检查 pymilvus / sentence-transformers 是否已配置。",
            code=503,
            status_code=503,
        )
    except Exception as exc:
        raise DatabaseError("语义检索失败", detail=str(exc))

    data = [
        SearchResponseItem(
            chunk_id=h.get("chunk_id", ""),
            doc_id=h.get("doc_id", ""),
            text=h.get("text", ""),
            level_1=h.get("level_1", ""),
            level_2=h.get("level_2", ""),
            is_summary=h.get("is_summary", False),
            distance=h.get("distance", 0.0),
        )
        for h in hits
    ]

    return {"code": 200, "message": "检索成功", "data": data}
