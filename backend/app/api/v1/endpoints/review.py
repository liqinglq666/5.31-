"""
api/v1/endpoints/review.py
--------------------------
审查结果与数据洞察接口（合并自 stats.py + charts.py + dashboard.py）。

提供：
- 全局统计 (/api/v1/stats)
- 风险趋势 (/api/v1/chart/trend)
- 条款分布 (/api/v1/chart/clause-distribution)
- Dashboard 雷达图与洞察 (/api/v1/dashboard/*)
- Copilot 上下文 (/api/v1/copilot/context-chat)
"""

import logging
import traceback
from datetime import datetime, timedelta
from typing import Optional
from io import BytesIO

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_or_guest
from app.core.exceptions import DatabaseError
from app.models.models import TaskRecord, User
from app.crud.crud_task import (
    count_tasks,
    get_avg_duration,
    get_tasks_by_date_range,
    get_tasks_by_ids,
    get_history_records,
    list_tasks,
    get_task_db,
    archive_task_db,
    remark_task_db,
)
from app.services.dashboard_service import DashboardService, CopilotService, InsightService
from app.schemas.stats import (
    DashboardStatsResponse,
    DashboardInsightsResponse,
    InsightItem,
    CopilotContextResponse,
    CopilotSuggestion,
    StatsData,
    RadarChartData,
    RadarIndicator,
    RadarSeriesData,
)
from app.schemas.task import RemarkRequest

router = APIRouter()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/api/v1/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """聚合统计数据接口。"""
    try:
        total_reviews = await count_tasks(db)
        today_new = await count_tasks(db, today_only=True)
        completed_count = await count_tasks(db, status="completed")
        high_risk_count = await count_tasks(db, status="completed", is_high_risk=True)
        high_risk_ratio = round(high_risk_count / completed_count, 4) if completed_count > 0 else 0.0
        avg_duration_seconds = await get_avg_duration(db)

        return {
            "code": 200,
            "message": "查询成功",
            "data": {
                "total_reviews": total_reviews,
                "today_new": today_new,
                "high_risk_ratio": high_risk_ratio,
                "avg_duration_seconds": avg_duration_seconds,
            },
        }
    except Exception as e:
        logger.error("[Stats Error] %s", e, exc_info=True)
        raise DatabaseError("统计查询失败", detail=str(e))


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

@router.get("/api/v1/chart/trend")
async def get_trend(db: AsyncSession = Depends(get_db)):
    """近7天风险趋势数据。"""
    try:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=6)

        date_map = {}
        for i in range(7):
            d = (start_date + timedelta(days=i)).isoformat()
            date_map[d] = {"total": 0, "risk": 0}

        records = await get_tasks_by_date_range(db, start_date, end_date)
        for r in records:
            d = r.created_at.date().isoformat() if r.created_at else None
            if d and d in date_map:
                date_map[d]["total"] += 1
                risk = (r.result or {}).get("comparison", {}).get("risk_level", "")
                if risk == "high":
                    date_map[d]["risk"] += 1

        dates = list(date_map.keys())
        return {
            "code": 200,
            "message": "查询成功",
            "data": {
                "dates": dates,
                "totals": [date_map[d]["total"] for d in dates],
                "risks": [date_map[d]["risk"] for d in dates],
            },
        }
    except Exception as e:
        raise DatabaseError("趋势数据查询失败", detail=str(e))


@router.get("/api/v1/chart/clause-distribution")
async def get_clause_distribution(db: AsyncSession = Depends(get_db)):
    """风险条款分布数据（饼图）。"""
    try:
        result = await db.execute(
            select(TaskRecord).where(TaskRecord.status == "completed")
        )
        records = result.scalars().all()

        distribution = {
            "付款条款": 0,
            "交付周期": 0,
            "违约责任": 0,
            "供应商信息": 0,
            "其他": 0,
        }

        for r in records:
            comparison = (r.result or {}).get("comparison", {})
            differences = comparison.get("differences", [])
            missing_items = comparison.get("missing_items", [])
            all_issues = differences + missing_items
            for item in all_issues:
                diff_text = item.get("description", "") if isinstance(item, dict) else str(item)
                if "一致" in diff_text and len(all_issues) == 1:
                    continue
                if "金额" in diff_text:
                    distribution["付款条款"] += 1
                elif "天数" in diff_text or "交期" in diff_text:
                    distribution["交付周期"] += 1
                elif "违约金" in diff_text or "违约" in diff_text:
                    distribution["违约责任"] += 1
                elif "供应商" in diff_text:
                    distribution["供应商信息"] += 1
                else:
                    distribution["其他"] += 1

        data = [{"name": k, "value": v} for k, v in distribution.items() if v > 0]
        return {
            "code": 200,
            "message": "查询成功",
            "data": data,
        }
    except Exception as e:
        raise DatabaseError("条款分布查询失败", detail=str(e))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/api/v1/dashboard/stats", response_model=dict)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_guest),
):
    """
    获取 Dashboard 统计数据，包含雷达图五个维度评分。
    """
    try:
        dashboard_service = DashboardService(db)
        recent_tasks = await dashboard_service.get_recent_tasks(limit=20)
        radar_data = dashboard_service.calculate_radar_data(recent_tasks)

        total_reviews = await count_tasks(db)
        today_new = await count_tasks(db, today_only=True)
        completed_count = await count_tasks(db, status="completed")
        high_risk_count = await count_tasks(db, status="completed", is_high_risk=True)
        high_risk_ratio = round(high_risk_count / completed_count, 4) if completed_count > 0 else 0.0
        avg_duration_seconds = await get_avg_duration(db)

        return {
            "code": 200,
            "message": "查询成功",
            "data": {
                "total_reviews": total_reviews,
                "today_new": today_new,
                "high_risk_ratio": high_risk_ratio,
                "avg_duration_seconds": avg_duration_seconds,
                "radar": radar_data,
            },
        }
    except Exception as e:
        logger.error(f"[Dashboard Stats Error] {e}")
        traceback.print_exc()
        raise DatabaseError("统计数据查询失败", detail=str(e))


@router.get("/api/v1/dashboard/insights", response_model=dict)
async def get_dashboard_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_guest),
):
    """生成宏观洞察流。"""
    try:
        dashboard_service = DashboardService(db)
        recent_tasks = await dashboard_service.get_recent_tasks(limit=20)
        insights_raw = await dashboard_service.generate_insights(recent_tasks)

        insights = [
            InsightItem(
                type=item.get("type", "info"),
                tag=item.get("tag", "洞察"),
                content=item.get("content", ""),
                action_text=item.get("action_text", "查看详情"),
            )
            for item in insights_raw
        ]

        return {
            "code": 200,
            "message": "洞察生成成功",
            "data": {
                "insights": insights,
                "generated_at": datetime.now().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"[Dashboard Insights Error] {e}")
        traceback.print_exc()
        raise DatabaseError("洞察生成失败", detail=str(e))


@router.get("/api/v1/dashboard/insights/latest", response_model=dict)
async def get_latest_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_guest),
):
    """获取最新的 AI 洞察（从数据库读取）。"""
    try:
        insight_service = InsightService(db)
        data = await insight_service.get_latest_insights()

        insights = [
            InsightItem(
                type=item.get("type", "info"),
                tag=item.get("tag", "洞察"),
                content=item.get("content", ""),
                action_text=item.get("action_text", "查看详情"),
            )
            for item in data["insights"]
        ]

        return {
            "code": 200,
            "message": "查询成功",
            "data": {
                "insights": insights,
                "sample_count": data["sample_count"],
                "generated_at": data["generated_at"],
                "is_fresh": data["is_fresh"],
            },
        }
    except Exception as e:
        logger.error(f"[Get Latest Insights Error] {e}")
        traceback.print_exc()
        raise DatabaseError("获取洞察失败", detail=str(e))


@router.post("/api/v1/dashboard/insights/refresh", response_model=dict)
async def refresh_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_guest),
):
    """刷新 AI 洞察。"""
    try:
        insight_service = InsightService(db)
        data = await insight_service.refresh_insights(user_id=str(current_user.id))

        insights = [
            InsightItem(
                type=item.get("type", "info"),
                tag=item.get("tag", "洞察"),
                content=item.get("content", ""),
                action_text=item.get("action_text", "查看详情"),
            )
            for item in data["insights"]
        ]

        return {
            "code": 200,
            "message": "刷新成功",
            "data": {
                "insights": insights,
                "sample_count": data["sample_count"],
                "generated_at": data["generated_at"],
                "is_fresh": True,
            },
        }
    except Exception as e:
        logger.error(f"[Refresh Insights Error] {e}")
        traceback.print_exc()
        raise DatabaseError("刷新洞察失败", detail=str(e))


@router.get("/api/v1/copilot/context-chat", response_model=dict)
async def get_copilot_context(
    page_id: str = Query(..., description="当前页面ID，如 dashboard, compare, records, audit"),
    item_id: Optional[str] = Query(None, description="可选的项目ID，如合同任务ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_or_guest),
):
    """获取上下文感知的 Copilot 开场白和建议。"""
    try:
        copilot_service = CopilotService(db)
        context = await copilot_service.get_context(page_id, item_id)

        suggestions = [
            CopilotSuggestion(text=s.get("text", ""), action=s.get("action"))
            for s in context.get("suggestions", [])
        ]

        return {
            "code": 200,
            "message": "获取成功",
            "data": {
                "page_id": page_id,
                "greeting": context.get("greeting", ""),
                "context_summary": context.get("context_summary", ""),
                "suggestions": suggestions,
            },
        }
    except Exception as e:
        logger.error(f"[Copilot Context Error] {e}")
        traceback.print_exc()
        raise DatabaseError("Copilot 上下文获取失败", detail=str(e))
