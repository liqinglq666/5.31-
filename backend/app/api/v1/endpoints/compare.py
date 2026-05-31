import asyncio
import os
import tempfile
import uuid

from typing import List
from fastapi import APIRouter, UploadFile, File, Depends, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.database import get_db
from app.core.exceptions import FileError
from app.models.models import User
from app.crud.crud_task import create_task_db, get_task_db, update_task_db
from app.application.tasks import process_compare_task, cancel_compare_task
from app.core.exceptions import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# 限制并发后台比对任务数，防止大文件解析 + LLM 调用同时爆发导致 OOM
_COMPARE_SEMAPHORE = asyncio.Semaphore(5)


@router.post("/api/v1/compare")
async def compare_documents(
    procurement: UploadFile = File(..., description="采购结果文件（PDF/Word 等）"),
    contract: UploadFile = File(..., description="合同文件（PDF/Word 等）"),
    model_id: str | None = Form(default=None, description="指定 LLM 模型 ID"),
    price_tolerance: float = Form(default=0.0, ge=0.0, description="金额容差百分比，如 5.0 表示 ±5%"),
    required_clauses: List[str] = Form(default_factory=list, description="必检条款名称清单"),
    custom_requirements: str = Form(default="", description="用户自定义的额外审查要求或输出格式要求"),
    enable_visual_localization: bool = Query(
        default=False, description="是否启用 PDF 原文空间坐标定位（视觉溯源）"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    接收采购结果与合同两份文件，创建审查任务并立即返回 task_id。
    实际执行完整的五阶段合同审查流水线（Docling 解析 → 记忆构建 → 提取预检 → 双 Agent 审查 → CoVe 终审）。
    """
    task_id = str(uuid.uuid4())
    await create_task_db(
        db,
        task_id=task_id,
        file_a_name=procurement.filename,
        file_b_name=contract.filename,
        creator_id=current_user.id,
    )

    procurement_bytes = await procurement.read()
    contract_bytes = await contract.read()

    tmp_dir = tempfile.gettempdir()
    bid_ext = os.path.splitext(procurement.filename or "")[1] or ".pdf"
    contract_ext = os.path.splitext(contract.filename or "")[1] or ".pdf"
    bid_path = os.path.join(tmp_dir, f"{task_id}_bid{bid_ext}")
    contract_path = os.path.join(tmp_dir, f"{task_id}_contract{contract_ext}")

    try:
        with open(bid_path, "wb") as f:
            f.write(procurement_bytes)
        with open(contract_path, "wb") as f:
            f.write(contract_bytes)
    except Exception as exc:
        raise FileError(f"文件保存失败，请检查上传文件: {exc}")

    async def _run_with_semaphore() -> None:
        async with _COMPARE_SEMAPHORE:
            try:
                await process_compare_task(
                    task_id,
                    bid_path,
                    contract_path,
                    model_id=model_id,
                    price_tolerance=price_tolerance,
                    required_clauses=required_clauses,
                    custom_requirements=custom_requirements,
                    enable_visual_localization=enable_visual_localization,
                )
            finally:
                # 清理本地临时文件，避免磁盘堆积
                for p in (bid_path, contract_path):
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass

    asyncio.create_task(_run_with_semaphore())

    return {
        "code": 200,
        "message": "任务已创建，正在后台执行审查",
        "data": {"task_id": task_id, "status": "pending"},
    }


@router.post("/api/v1/compare/{task_id}/cancel")
async def cancel_compare(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    """取消正在运行的比对任务。若任务不在内存中但仍在数据库为 pending/processing，则直接更新状态。"""
    cancelled = await cancel_compare_task(task_id)
    if not cancelled:
        task = await get_task_db(db, task_id)
        if task and task.status in ("pending", "processing"):
            await update_task_db(
                db,
                task_id=task_id,
                status="cancelled",
                message="任务已取消",
                progress=0,
            )
        else:
            raise NotFoundError("任务不存在或已结束")
    return {
        "code": 200,
        "message": "任务已取消",
        "data": {"task_id": task_id, "status": "cancelled"},
    }
