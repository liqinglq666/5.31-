"""
api/v1/endpoints/supplier.py
---------------------------
供应商画像与历史比对记录真实数据 API。
所有数据 100% 来自 PostgreSQL，零 Mock。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.exceptions import ValidationError, NotFoundError
from app.models.models import User, TaskRecord
from app.models.memory import SupplierProfile

router = APIRouter()


@router.get("/api/v1/suppliers/profile/{supplier_name}")
async def get_supplier_profile(
    supplier_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    根据供应商名称查询画像及最近 10 条比对记录。
    Query 1: 精确匹配 supplier_profiles 表。
    Query 2: 精确匹配 task_records 表，按 created_at DESC LIMIT 10。
    """
    if not supplier_name or not supplier_name.strip():
        raise ValidationError("供应商名称不能为空")

    name = supplier_name.strip()

    # ---------- Query 1: 供应商画像 ----------
    profile_result = await db.execute(
        select(SupplierProfile).where(SupplierProfile.supplier_name == name)
    )
    profile: Optional[SupplierProfile] = profile_result.scalar_one_or_none()

    if profile is None:
        raise NotFoundError("该供应商暂无画像")

    # ---------- Query 2: 最近比对记录 ----------
    task_result = await db.execute(
        select(TaskRecord)
        .where(TaskRecord.supplier_name == name)
        .order_by(TaskRecord.created_at.desc())
        .limit(10)
        .options(selectinload(TaskRecord.creator))
    )
    recent_tasks: List[TaskRecord] = list(task_result.scalars().all())

    recent_contracts = []
    for task in recent_tasks:
        risk_level = "low"
        if task.result and isinstance(task.result, dict):
            comparison = task.result.get("comparison") or {}
            risk_level = comparison.get("risk_level", "low")

        recent_contracts.append({
            "task_id": task.id,
            "contract_name": task.file_b_name or "未知合同",
            "date": task.created_at.isoformat() if task.created_at else None,
            "risk_level": risk_level,
            "creator_name": task.creator.full_name if task.creator else None,
        })

    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "supplier_name": profile.supplier_name,
            "total_contracts": profile.total_contracts or 0,
            "frequent_missing_clauses": profile.frequent_missing_clauses or [],
            "risk_summary": profile.risk_summary or "",
            "recent_contracts": recent_contracts,
        },
    }
