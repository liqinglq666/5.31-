import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.crud.crud_task import get_task_with_creator

router = APIRouter()

_BEIJING_TZ = timezone(timedelta(hours=8))


def fmt_bj(dt):
    """将 UTC 时间格式化为北京时间字符串（YYYY/MM/DD HH:mm:ss）。"""
    if dt is None:
        return None
    utc_dt = dt.replace(tzinfo=timezone.utc)
    bj_dt = utc_dt.astimezone(_BEIJING_TZ)
    return bj_dt.strftime("%Y/%m/%d %H:%M:%S")


@router.get("/api/v1/status/{task_id}")
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_db)):
    """根据 task_id 查询任务当前处理进度与结果。"""
    record = await get_task_with_creator(db, task_id)
    if record is None:
        raise NotFoundError("任务不存在，请检查 task_id 是否正确")

    creator = record.creator

    # === DEBUG 日志（生产环境可通过日志级别关闭）===
    result_data = record.result or {}
    diffs = []
    if isinstance(result_data, dict):
        comp = result_data.get("comparison") or {}
        if isinstance(comp, dict):
            diffs = comp.get("differences", [])
    if diffs:
        logger.debug("[API DEBUG] 即将发送给前端的差异项（前3条）：")
        for idx in range(min(3, len(diffs))):
            d = diffs[idx]
            if isinstance(d, dict):
                logger.debug(
                    "  [%d] type=%s desc=%s orig=%s cont=%s",
                    idx + 1,
                    d.get("type", "(无type)"),
                    (d.get("description") or "")[:60],
                    (d.get("original_text") or "")[:60],
                    (d.get("contract_text") or "")[:60],
                )
            else:
                logger.debug("  [%d] 非字典项: %s", idx + 1, d)
    # === 调试结束 ===

    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "task_id": record.id,
            "status": record.status,
            "message": record.message,
            "progress": record.progress,
            "result": record.result,
            "process_mode": record.process_mode,
            "model_name": record.model_name,
            "processing_seconds": record.processing_seconds,
            "created_at": fmt_bj(record.created_at),
            "creator_name": creator.full_name if creator else None,
            "creator_emp_id": creator.employee_id if creator else None,
        },
    }
