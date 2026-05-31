"""
crud/crud_task.py
-----------------
任务记录的基础增删改查逻辑。
"""

from typing import Optional, Dict, Any, List
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import TaskRecord, utc_now


async def create_task_db(
    db: AsyncSession,
    task_id: str,
    file_a_name: Optional[str] = None,
    file_b_name: Optional[str] = None,
    creator_id: Optional[str] = None,
) -> TaskRecord:
    """在数据库中创建一条新的 pending 记录。"""
    record = TaskRecord(
        id=task_id,
        file_a_name=file_a_name,
        file_b_name=file_b_name,
        status="pending",
        progress=0,
        message="任务已创建，等待执行",
        creator_id=creator_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_task_db(db: AsyncSession, task_id: str) -> Optional[TaskRecord]:
    """根据 task_id 查询数据库中的任务记录。"""
    result = await db.execute(select(TaskRecord).where(TaskRecord.id == task_id))
    return result.scalar_one_or_none()


async def get_task_with_creator(db: AsyncSession, task_id: str) -> Optional[TaskRecord]:
    """根据 task_id 查询任务记录，并预加载创建人信息。"""
    result = await db.execute(
        select(TaskRecord)
        .where(TaskRecord.id == task_id)
        .options(selectinload(TaskRecord.creator))
    )
    return result.scalar_one_or_none()


async def update_task_db(
    db: AsyncSession,
    task_id: str,
    status: Optional[str] = None,
    message: Optional[str] = None,
    progress: Optional[int] = None,
    result: Optional[Dict[str, Any]] = None,
    file_a_name: Optional[str] = None,
    file_b_name: Optional[str] = None,
    process_mode: Optional[str] = None,
    supplier_name: Optional[str] = None,
    model_name: Optional[str] = None,
    processing_seconds: Optional[int] = None,
) -> Optional[TaskRecord]:
    """更新数据库中指定任务记录的状态、进度或结果。"""
    record = await get_task_db(db, task_id)
    if record is None:
        return None

    if status is not None:
        record.status = status
        if status == "completed" and record.completed_at is None:
            record.completed_at = utc_now()
    if message is not None:
        record.message = message
    if progress is not None:
        record.progress = progress
    if result is not None:
        record.result = result
    if file_a_name is not None:
        record.file_a_name = file_a_name
    if file_b_name is not None:
        record.file_b_name = file_b_name
    if process_mode is not None:
        record.process_mode = process_mode
    if supplier_name is not None:
        record.supplier_name = supplier_name
    if model_name is not None:
        record.model_name = model_name
    if processing_seconds is not None:
        record.processing_seconds = processing_seconds

    await db.commit()
    await db.refresh(record)
    return record


async def archive_task_db(
    db: AsyncSession,
    task_id: str,
    reviewer_id: str,
) -> Optional[TaskRecord]:
    """归档任务：设置 is_archived=True，记录归档时间和审查人。"""
    record = await get_task_db(db, task_id)
    if record is None:
        return None
    record.is_archived = True
    record.archive_time = utc_now()
    record.reviewer_id = reviewer_id
    await db.commit()
    await db.refresh(record)
    return record


async def remark_task_db(
    db: AsyncSession,
    task_id: str,
    remark: str,
    reviewer_id: str,
) -> Optional[TaskRecord]:
    """添加/更新任务备注。"""
    record = await get_task_db(db, task_id)
    if record is None:
        return None
    record.remark = remark
    record.remark_time = utc_now()
    record.remark_reviewer_id = reviewer_id
    await db.commit()
    await db.refresh(record)
    return record


async def list_tasks(
    db: AsyncSession,
    *,
    creator_id: Optional[str] = None,
    keyword: Optional[str] = None,
    risk_level: Optional[str] = None,
    scope: Optional[str] = None,
    is_admin: bool = False,
    is_archived: Optional[bool] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> tuple[List[TaskRecord], int]:
    """
    分页查询任务列表，支持关键词搜索、风险等级筛选、权限范围过滤。

    Returns:
        (记录列表, 总条数)
    """
    query = select(TaskRecord)

    # 权限过滤
    if scope != "all" or not is_admin:
        if creator_id is not None:
            query = query.where(TaskRecord.creator_id == creator_id)
    elif creator_id and creator_id.strip():
        query = query.where(TaskRecord.creator_id == creator_id.strip())

    if keyword and keyword.strip():
        like_pattern = f"%{keyword.strip()}%"
        query = query.where(
            (TaskRecord.file_a_name.ilike(like_pattern))
            | (TaskRecord.file_b_name.ilike(like_pattern))
        )

    if risk_level and risk_level.strip():
        rl = risk_level.strip().lower()
        if rl == "safe":
            query = query.where(
                TaskRecord.result["comparison"]["risk_level"].as_string() == "low"
            )
        else:
            query = query.where(
                TaskRecord.result["comparison"]["risk_level"].as_string() == rl
            )

    if is_archived is not None:
        query = query.where(TaskRecord.is_archived == is_archived)

    if status and status.strip():
        query = query.where(TaskRecord.status == status.strip())

    # 总数
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # 分页
    page_query = (
        query.order_by(TaskRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .options(selectinload(TaskRecord.creator))
        .options(selectinload(TaskRecord.reviewer))
        .options(selectinload(TaskRecord.remark_reviewer))
    )
    result = await db.execute(page_query)
    records = result.scalars().all()

    return list(records), total


async def get_tasks_by_ids(db: AsyncSession, task_ids: List[str]) -> List[TaskRecord]:
    """根据 ID 列表批量查询任务记录。"""
    result = await db.execute(select(TaskRecord).where(TaskRecord.id.in_(task_ids)))
    return list(result.scalars().all())


async def get_tasks_by_date_range(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[TaskRecord]:
    """查询指定日期范围内的任务记录。"""
    query = select(TaskRecord)
    if start_date is not None:
        query = query.where(func.date(TaskRecord.created_at) >= start_date)
    if end_date is not None:
        query = query.where(func.date(TaskRecord.created_at) <= end_date)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_completed_tasks(db: AsyncSession) -> List[TaskRecord]:
    """查询所有已完成的任务记录。"""
    result = await db.execute(
        select(TaskRecord).where(TaskRecord.status == "completed")
    )
    return list(result.scalars().all())


async def count_tasks(
    db: AsyncSession,
    *,
    status: Optional[str] = None,
    is_high_risk: bool = False,
    today_only: bool = False,
) -> int:
    """统计任务数量，支持按状态、风险等级和今日筛选。"""
    query = select(func.count(TaskRecord.id))
    if status:
        query = query.where(TaskRecord.status == status)
    if today_only:
        from datetime import datetime
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(TaskRecord.created_at >= today_start)
    if is_high_risk:
        query = query.where(
            TaskRecord.status == "completed",
            TaskRecord.result.isnot(None),
            TaskRecord.result["comparison"]["risk_level"].as_string() == "high",
        )
    result = await db.execute(query)
    return result.scalar() or 0


async def get_avg_duration(db: AsyncSession) -> float:
    """计算已完成任务的平均比对耗时（秒）。"""
    result = await db.execute(
        select(
            func.coalesce(
                func.avg(func.extract("epoch", TaskRecord.completed_at - TaskRecord.created_at)),
                0,
            )
        ).where(
            TaskRecord.status == "completed",
            TaskRecord.completed_at.isnot(None),
        )
    )
    avg = result.scalar() or 0
    return round(float(avg), 2)


async def get_history_records(
    db: AsyncSession,
    *,
    creator_id: Optional[str] = None,
    scope: Optional[str] = None,
    is_admin: bool = False,
) -> List[TaskRecord]:
    """按时间倒序查询历史比对记录。"""
    query = select(TaskRecord).order_by(TaskRecord.created_at.desc())
    if scope != "all" or not is_admin:
        query = query.where(TaskRecord.creator_id == creator_id)
    result = await db.execute(query)
    return list(result.scalars().all())
