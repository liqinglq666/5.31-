"""
crud/crud_user.py
-----------------
用户基础增删改查逻辑。
"""

from typing import Optional, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User, TaskRecord
from app.core.security import get_password_hash


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    """根据用户 ID 查询用户。"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """根据用户名查询用户。"""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    full_name: Optional[str] = None,
    employee_id: Optional[str] = None,
    position: Optional[str] = None,
    status: str = "pending",
    is_admin: bool = False,
) -> User:
    """创建新用户。"""
    user = User(
        username=username,
        password_hash=get_password_hash(password),
        full_name=full_name,
        employee_id=employee_id,
        position=position,
        status=status,
        is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_status(
    db: AsyncSession,
    user_id: str,
    status: str,
) -> Optional[User]:
    """更新用户状态。"""
    user = await get_user_by_id(db, user_id)
    if user is None:
        return None
    user.status = status
    await db.commit()
    await db.refresh(user)
    return user


async def list_pending_users(db: AsyncSession) -> List[User]:
    """查询所有待审批用户。"""
    result = await db.execute(select(User).where(User.status == "pending"))
    return list(result.scalars().all())


async def list_all_users_with_task_count(db: AsyncSession) -> List[tuple[User, int]]:
    """
    获取系统内所有用户列表（包含任务总数）。
    Returns:
        [(User, task_count), ...]
    """
    stmt = (
        select(User, func.count(TaskRecord.id).label("task_count"))
        .outerjoin(TaskRecord, User.id == TaskRecord.creator_id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    result = await db.execute(stmt)
    return [(user, task_count or 0) for user, task_count in result.all()]
