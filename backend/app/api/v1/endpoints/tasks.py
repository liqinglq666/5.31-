"""
api/v1/endpoints/tasks.py
-------------------------
任务管理接口（合并自 history.py + records.py + archive.py + remark.py + export.py）。

提供：
- 历史记录查询 (/api/v1/history)
- 分页记录列表 (/api/v1/records)
- 任务归档 (/api/v1/tasks/{task_id}/archive)
- 任务备注 (/api/v1/tasks/{task_id}/remark)
- Excel 导出 (/api/v1/export/excel)
"""

from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_or_guest
from app.core.exceptions import NotFoundError, ConflictError, ValidationError, DatabaseError
from app.models.models import User
from app.crud.crud_task import (
    get_history_records,
    list_tasks,
    get_task_db,
    archive_task_db,
    remark_task_db,
    get_tasks_by_ids,
)
from app.schemas.task import RemarkRequest

router = APIRouter()

_BEIJING_TZ = timezone(timedelta(hours=8))


def fmt_bj(dt: Optional[datetime]) -> Optional[str]:
    """将 UTC 时间格式化为北京时间字符串（YYYY/MM/DD HH:mm:ss）。"""
    if dt is None:
        return None
    utc_dt = dt.replace(tzinfo=timezone.utc)
    bj_dt = utc_dt.astimezone(_BEIJING_TZ)
    return bj_dt.strftime("%Y/%m/%d %H:%M:%S")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/api/v1/history")
async def get_history(
    scope: str = Query("", description="传 all 表示全公司，仅管理员可用"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按时间倒序查询历史比对记录。默认只返回当前用户创建的记录，管理员传 scope=all 可查看全公司。"""
    records = await get_history_records(
        db,
        creator_id=current_user.id,
        scope=scope or None,
        is_admin=current_user.is_admin,
    )
    return {
        "code": 200,
        "message": "查询成功",
        "data": [
            {
                "task_id": r.id,
                "file_a_name": r.file_a_name,
                "file_b_name": r.file_b_name,
                "status": r.status,
                "message": r.message,
                "progress": r.progress,
                "result": r.result,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
    }


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@router.get("/api/v1/records")
async def get_records(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    keyword: str = Query("", description="项目名称模糊搜索"),
    risk_level: str = Query("", description="风险等级筛选: high / low / safe"),
    scope: str = Query("", description="传 all 表示全公司，仅管理员可用"),
    creator_id: str = Query("", description="创建人ID筛选，仅管理员可用"),
    is_archived: Optional[bool] = Query(None, description="是否只显示已归档记录，None 表示不筛选"),
    status: str = Query("", description="任务状态筛选: pending / processing / completed / failed / cancelled"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_guest),
):
    """分页列表接口，支持按项目名称模糊搜索、按风险等级筛选。
    默认只返回当前用户创建的记录，管理员传 scope=all 可查看全公司。
    游客仅可查看最新 5 条已完成的任务记录，不支持搜索和筛选。
    """
    try:
        is_guest = current_user.id == "guest"

        effective_creator_id = current_user.id
        if not is_guest and current_user.is_admin and scope == "all":
            effective_creator_id = creator_id if creator_id else None

        if is_guest:
            page = 1
            page_size = 5
            keyword = None
            risk_level = None
            is_archived = None
            status = "completed"
            effective_creator_id = None
            scope = "all"

        records, total = await list_tasks(
            db,
            creator_id=effective_creator_id,
            keyword=keyword or None,
            risk_level=risk_level or None,
            scope=scope or None,
            is_admin=current_user.is_admin if not is_guest else False,
            is_archived=is_archived,
            status=status or None,
            page=page,
            page_size=page_size,
        )

        data = []
        for r in records:
            comparison = (r.result or {}).get("comparison", {})
            creator = r.creator
            reviewer = r.reviewer
            remark_reviewer = r.remark_reviewer
            data.append(
                {
                    "task_id": r.id,
                    "project_name": r.file_a_name or r.file_b_name or "未命名项目",
                    "created_at": fmt_bj(r.created_at),
                    "status": r.status,
                    "risk_level": comparison.get("risk_level", "unknown"),
                    "conclusion": r.message or "",
                    "creator_id": creator.id if creator else None,
                    "creator_name": creator.full_name if creator else None,
                    "creator_emp_id": creator.employee_id if creator else None,
                    "is_archived": r.is_archived,
                    "archive_time": fmt_bj(r.archive_time),
                    "reviewer_name": reviewer.full_name if reviewer else None,
                    "reviewer_emp_id": reviewer.employee_id if reviewer else None,
                    "remark": r.remark,
                    "remark_time": fmt_bj(r.remark_time),
                    "remark_reviewer_name": remark_reviewer.full_name if remark_reviewer else None,
                    "remark_reviewer_emp_id": remark_reviewer.employee_id if remark_reviewer else None,
                    "model_name": r.model_name,
                    "processing_seconds": r.processing_seconds,
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
    except Exception as e:
        import traceback
        print(f"[Records Error] {e}")
        traceback.print_exc()
        raise DatabaseError("记录查询失败", detail=str(e))


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

@router.post("/api/v1/tasks/{task_id}/archive")
async def archive_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """归档任务：设置 is_archived=True，记录归档时间和审查人。"""
    task = await get_task_db(db, task_id)
    if not task:
        raise NotFoundError("任务不存在")
    if task.is_archived:
        raise ConflictError("该任务已被归档")

    record = await archive_task_db(db, task_id, current_user.id)
    return {
        "code": 200,
        "message": "归档成功",
        "task_id": record.id,
        "archive_time": record.archive_time.isoformat() if record.archive_time else None,
    }


# ---------------------------------------------------------------------------
# Remark
# ---------------------------------------------------------------------------

@router.post("/api/v1/tasks/{task_id}/remark")
async def add_remark(
    task_id: str,
    body: RemarkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为任务添加/更新备注信息。"""
    task = await get_task_db(db, task_id)
    if not task:
        raise NotFoundError("任务不存在")

    record = await remark_task_db(db, task_id, body.remark, current_user.id)
    return {
        "code": 200,
        "message": "备注已保存",
        "task_id": record.id,
        "remark": record.remark,
        "remark_time": record.remark_time.isoformat() if record.remark_time else None,
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/api/v1/export/excel")
async def export_excel(
    task_ids: str = Query(..., description="逗号分隔的任务 ID 列表"),
    db: AsyncSession = Depends(get_db),
):
    """Excel 导出接口。"""
    if not task_ids.strip():
        raise ValidationError("task_ids 不能为空")

    id_list = [tid.strip() for tid in task_ids.split(",") if tid.strip()]
    if not id_list:
        raise ValidationError("task_ids 格式错误")

    records = await get_tasks_by_ids(db, id_list)

    wb = Workbook()
    ws = wb.active
    ws.title = "比对记录"
    ws.append(["项目名称", "比对结论", "风险点摘要"])

    for r in records:
        project_name = r.file_a_name or r.file_b_name or "未命名项目"
        conclusion = r.message or ""
        comparison = (r.result or {}).get("comparison", {})
        differences = comparison.get("differences", [])
        missing_items = comparison.get("missing_items", [])
        all_issues = differences + missing_items
        def _fmt(item):
            return item.get("description", "") if isinstance(item, dict) else str(item)
        risk_summary = "；".join(_fmt(it) for it in all_issues) if all_issues else "无"
        ws.append([project_name, conclusion, risk_summary])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=compare_records.xlsx"},
    )


# ---------------------------------------------------------------------------
# Running tasks (task center)
# ---------------------------------------------------------------------------

@router.get("/api/v1/tasks/running")
async def get_running_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_guest),
):
    """获取任务中心数据：
    - 当前用户的 pending / processing 任务
    - 全局最近 10 条已完成的比对记录（所有人可见）
    """
    is_guest = current_user.id == "guest"

    all_records = []

    # 1. pending / processing 任务（仅自己的）
    if not is_guest:
        records, _ = await list_tasks(
            db,
            creator_id=current_user.id,
            scope=None,
            is_admin=False,
            status="pending",
            page=1,
            page_size=100,
        )
        records2, _ = await list_tasks(
            db,
            creator_id=current_user.id,
            scope=None,
            is_admin=False,
            status="processing",
            page=1,
            page_size=100,
        )
        all_records.extend(records)
        all_records.extend(records2)

    # 2. 全局最近 10 条 completed（所有人可见）
    completed_records, _ = await list_tasks(
        db,
        creator_id=None,
        scope="all",
        is_admin=False,
        status="completed",
        page=1,
        page_size=10,
    )
    all_records.extend(completed_records)

    return {
        "code": 200,
        "message": "查询成功",
        "data": [
            {
                "task_id": r.id,
                "file_a_name": r.file_a_name,
                "file_b_name": r.file_b_name,
                "status": r.status,
                "message": r.message,
                "progress": r.progress,
                "process_mode": r.process_mode,
                "model_name": r.model_name,
                "processing_seconds": r.processing_seconds,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in all_records
        ],
    }
