"""
admin_router.py
---------------
管理员专用接口：审批用户、人员管理、审查记录查询、模型配置管理等。
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_admin_user
from app.core.database import get_db
from app.core.exceptions import NotFoundError, ConflictError, ValidationError
from app.models.models import User, SysModelConfig
from app.crud.crud_user import (
    get_user_by_id,
    list_pending_users,
    list_all_users_with_task_count,
    update_user_status,
)
from app.crud.crud_task import list_tasks
from app.infrastructure.llm.dynamic_config import (
    refresh_model_config_cache,
    encrypt_api_key,
    decrypt_api_key,
    mask_api_key,
)

router = APIRouter()


@router.get("/api/v1/admin/pending_users")
async def get_pending_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """查询所有待审批用户。"""
    users = await list_pending_users(db)
    return {
        "code": 200,
        "message": "查询成功",
        "data": [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "employee_id": u.employee_id,
                "position": u.position,
                "status": u.status,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    }


@router.post("/api/v1/admin/users/{user_id}/approve")
async def approve_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """将指定用户状态改为 active。"""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    if user.status == "active":
        raise ConflictError("该用户已是激活状态")

    await update_user_status(db, user_id, "active")
    return {"code": 200, "message": "审批通过", "user_id": user.id}


@router.get("/api/v1/admin/users")
async def get_all_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """获取系统内所有用户列表（包含任务总数），供管理员进行全量人员管理。"""
    rows = await list_all_users_with_task_count(db)

    data = []
    for user, task_count in rows:
        data.append(
            {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "employee_id": user.employee_id,
                "position": user.position,
                "status": user.status,
                "is_admin": user.is_admin,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "task_count": task_count,
            }
        )

    return {
        "code": 200,
        "message": "查询成功",
        "data": data,
    }


@router.post("/api/v1/admin/users/{user_id}/toggle_status")
async def toggle_user_status(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """切换用户状态：active <-> disabled。pending 用户不可直接切换。"""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    if user.status == "pending":
        raise ValidationError("待审批用户请先执行审批操作")
    if user.id == admin.id:
        raise ValidationError("不能禁用当前登录的管理员账号")

    new_status = "disabled" if user.status == "active" else "active"
    await update_user_status(db, user_id, new_status)
    return {
        "code": 200,
        "message": f"用户已{'禁用' if new_status == 'disabled' else '启用'}",
        "user_id": user.id,
        "status": new_status,
    }


@router.get("/api/v1/admin/users/{user_id}/records")
async def get_user_records(
    user_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """查询指定用户的全部审查历史记录。返回格式与 /api/v1/records 一致。"""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise NotFoundError("用户不存在")

    records, total = await list_tasks(
        db,
        creator_id=user_id,
        page=page,
        page_size=page_size,
    )

    data = []
    for r in records:
        comparison = (r.result or {}).get("comparison", {})
        creator = r.creator
        data.append(
            {
                "task_id": r.id,
                "project_name": r.file_a_name or r.file_b_name or "未命名项目",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "status": r.status,
                "risk_level": comparison.get("risk_level", "unknown"),
                "conclusion": r.message or "",
                "creator_name": creator.full_name if creator else None,
                "creator_emp_id": creator.employee_id if creator else None,
            }
        )

    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "list": data,
        },
    }


# -----------------------------------------------------------------------------
# 模型配置管理（动态热切换）
# -----------------------------------------------------------------------------

class ModelConfigCreate(BaseModel):
    provider: str
    model_name: str
    api_model_id: Optional[str] = None
    base_url: Optional[str] = None
    api_key: str
    temperature: Optional[str] = "0.0"
    is_active: bool = False


class ModelConfigUpdate(BaseModel):
    provider: Optional[str] = None
    model_name: Optional[str] = None
    api_model_id: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/api/v1/admin/models")
async def list_model_configs(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """返回所有模型配置列表（API Key 已脱敏）。"""
    result = await db.execute(select(SysModelConfig).order_by(SysModelConfig.id))
    configs = result.scalars().all()
    return {
        "code": 200,
        "message": "查询成功",
        "data": [
            {
                "id": c.id,
                "provider": c.provider,
                "model_name": c.model_name,
                "api_model_id": c.api_model_id,
                "base_url": c.base_url,
                "api_key": mask_api_key(
                    decrypt_api_key(c.encrypted_api_key) if c.encrypted_api_key else ""
                ),
                "temperature": c.temperature or "0.0",
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in configs
        ],
    }


@router.post("/api/v1/admin/models")
async def create_model_config(
    payload: ModelConfigCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """新增模型配置。若设为 is_active，自动取消其他激活项。"""
    if not payload.api_key or not payload.api_key.strip():
        raise ValidationError("API Key 不能为空")

    encrypted_key = encrypt_api_key(payload.api_key.strip())

    config = SysModelConfig(
        provider=payload.provider.strip(),
        model_name=payload.model_name.strip(),
        api_model_id=payload.api_model_id.strip() if payload.api_model_id else None,
        base_url=payload.base_url.strip() if payload.base_url else None,
        encrypted_api_key=encrypted_key,
        temperature=payload.temperature.strip() if payload.temperature else "0.0",
        is_active=payload.is_active,
    )
    db.add(config)
    await db.flush()

    if payload.is_active:
        await _clear_other_active(db, config.id)

    await db.commit()
    await refresh_model_config_cache()
    return {"code": 200, "message": "创建成功", "data": {"id": config.id}}


@router.put("/api/v1/admin/models/{model_id}")
async def update_model_config(
    model_id: int,
    payload: ModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """更新模型配置。若修改 is_active=True，自动取消其他激活项。"""
    result = await db.execute(
        select(SysModelConfig).where(SysModelConfig.id == model_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundError("模型配置不存在")

    if payload.provider is not None:
        config.provider = payload.provider.strip()
    if payload.model_name is not None:
        config.model_name = payload.model_name.strip()
    if payload.api_model_id is not None:
        config.api_model_id = payload.api_model_id.strip() if payload.api_model_id else None
    if payload.base_url is not None:
        config.base_url = payload.base_url.strip() if payload.base_url else None
    if payload.api_key is not None and payload.api_key.strip():
        config.encrypted_api_key = encrypt_api_key(payload.api_key.strip())
    if payload.temperature is not None:
        config.temperature = payload.temperature.strip() if payload.temperature else "0.0"
    if payload.is_active is not None:
        config.is_active = payload.is_active
        if payload.is_active:
            await _clear_other_active(db, config.id)

    await db.commit()
    await refresh_model_config_cache()
    return {"code": 200, "message": "更新成功"}


@router.delete("/api/v1/admin/models/{model_id}")
async def delete_model_config(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """删除模型配置。"""
    result = await db.execute(
        select(SysModelConfig).where(SysModelConfig.id == model_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundError("模型配置不存在")

    await db.delete(config)
    await db.commit()
    await refresh_model_config_cache()
    return {"code": 200, "message": "删除成功"}


@router.post("/api/v1/admin/models/{model_id}/set_active")
async def set_active_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """一键切换：将指定模型设为当前激活，其余取消激活。"""
    result = await db.execute(
        select(SysModelConfig).where(SysModelConfig.id == model_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundError("模型配置不存在")

    await _clear_other_active(db, config.id)
    config.is_active = True
    await db.commit()
    await refresh_model_config_cache()
    return {"code": 200, "message": f"已切换至 {config.model_name}", "data": {"model_name": config.model_name}}


async def _clear_other_active(db: AsyncSession, keep_id: int):
    """辅助：将除 keep_id 外的所有配置 is_active 置为 False。"""
    result = await db.execute(
        select(SysModelConfig).where(
            SysModelConfig.is_active == True, SysModelConfig.id != keep_id
        )
    )
    for other in result.scalars().all():
        other.is_active = False
