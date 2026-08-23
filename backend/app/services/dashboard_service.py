"""
services/dashboard_service.py
---------------------------
Dashboard 数据聚合与洞察生成服务。
使用原生 openai.AsyncOpenAI 替代 LangChain LLMService 单例，
保持与多模型注册表的一致性。
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from app.models.models import TaskRecord, utc_now
from app.infrastructure.llm.client import chat_completion


class DashboardService:
    """Dashboard 数据服务类"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_recent_tasks(self, limit: int = 20) -> List[TaskRecord]:
        """获取最近 N 条已完成的任务记录"""
        result = await self.db.execute(
            select(TaskRecord)
            .where(TaskRecord.status == "completed")
            .where(TaskRecord.result.isnot(None))
            .order_by(desc(TaskRecord.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Task 1: 统一纯数学评分（零字符串匹配 / 零正则推断）
    # ------------------------------------------------------------------
    def _score_by_risk_and_count(
        self, result: Dict[str, Any], weight: int
    ) -> float:
        """
        统一评分公式。
        基础分由 comparison.risk_level 决定，扣分 = 差异数 × 维度权重，保底 0 分。
        所有输入均来自已解析的结构化 JSON，无任何字符串匹配或正则推断。
        """
        comparison = result.get("comparison") or {}
        risk_level = comparison.get("risk_level", "low")
        diff_count = len(comparison.get("differences") or []) + len(
            comparison.get("missing_items") or []
        )

        base = {"high": 40, "medium": 65, "low": 90}.get(risk_level, 90)
        deduction = min(base, diff_count * weight)
        return max(0.0, round(base - deduction, 1))

    def _calculate_finance_score(self, result: Dict[str, Any]) -> float:
        return self._score_by_risk_and_count(result, weight=15)

    def _calculate_legal_score(self, result: Dict[str, Any]) -> float:
        return self._score_by_risk_and_count(result, weight=12)

    def _calculate_delivery_score(self, result: Dict[str, Any]) -> float:
        return self._score_by_risk_and_count(result, weight=10)

    def _calculate_breach_score(self, result: Dict[str, Any]) -> float:
        return self._score_by_risk_and_count(result, weight=8)

    def _calculate_credit_score(self, result: Dict[str, Any]) -> float:
        return self._score_by_risk_and_count(result, weight=5)

    @staticmethod
    def _safe_avg(scores: List[float], default: float = 60.0) -> float:
        """安全求平均：空列表返回默认值，结果钳制到 [0, 100]"""
        if not scores:
            return default
        return max(0.0, min(100.0, round(sum(scores) / len(scores), 1)))

    def calculate_radar_data(self, tasks: List[TaskRecord]) -> Dict[str, Any]:
        """
        计算雷达图数据：五个维度的平均分
        """
        if not tasks:
            return {
                "indicators": [
                    {"name": "财务", "max": 100},
                    {"name": "法务", "max": 100},
                    {"name": "交付", "max": 100},
                    {"name": "违约", "max": 100},
                    {"name": "信用", "max": 100},
                ],
                "series": [{"value": [60, 60, 60, 60, 60], "name": "平均得分"}],
            }

        finance_scores: List[float] = []
        legal_scores: List[float] = []
        delivery_scores: List[float] = []
        breach_scores: List[float] = []
        credit_scores: List[float] = []

        for task in tasks:
            if not task.result:
                continue
            result = task.result
            finance_scores.append(self._calculate_finance_score(result))
            legal_scores.append(self._calculate_legal_score(result))
            delivery_scores.append(self._calculate_delivery_score(result))
            breach_scores.append(self._calculate_breach_score(result))
            credit_scores.append(self._calculate_credit_score(result))

        avg_scores = [
            self._safe_avg(finance_scores),
            self._safe_avg(legal_scores),
            self._safe_avg(delivery_scores),
            self._safe_avg(breach_scores),
            self._safe_avg(credit_scores),
        ]

        return {
            "indicators": [
                {"name": "财务", "max": 100},
                {"name": "法务", "max": 100},
                {"name": "交付", "max": 100},
                {"name": "违约", "max": 100},
                {"name": "信用", "max": 100},
            ],
            "series": [{"value": avg_scores, "name": "近20份合同平均"}],
        }

    def _build_insights_context(self, tasks: List[TaskRecord]) -> str:
        """
        构建 LLM 洞察分析的上下文
        """
        context_parts = []
        context_parts.append(f"分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
        context_parts.append(f"样本数量：最近 {len(tasks)} 份已完成审查的合同")
        context_parts.append("")

        vendor_stats: Dict[str, Dict[str, Any]] = {}
        risk_levels = {"high": 0, "medium": 0, "low": 0}
        common_issues: Dict[str, int] = {}

        for task in tasks:
            if not task.result:
                continue

            result = task.result
            comparison = result.get("comparison", {})
            bid_info = result.get("bid_info", {})
            contract_info = result.get("contract_info", {})

            risk_level = comparison.get("risk_level", "low")
            risk_levels[risk_level] = risk_levels.get(risk_level, 0) + 1

            vendor_name = bid_info.get("vendor_name", "") or contract_info.get("vendor_name", "未知")
            if vendor_name not in vendor_stats:
                vendor_stats[vendor_name] = {"count": 0, "risk_levels": []}
            vendor_stats[vendor_name]["count"] += 1
            vendor_stats[vendor_name]["risk_levels"].append(risk_level)

            # 提取差异描述（兼容新旧格式：旧为 str，新为 dict）
            differences = comparison.get("differences", [])
            missing_items = comparison.get("missing_items", [])
            all_issues = differences + missing_items
            for item in all_issues:
                if isinstance(item, dict):
                    diff_text = item.get("description", "")[:100]
                else:
                    diff_text = str(item)[:100]
                if diff_text:
                    common_issues[diff_text] = common_issues.get(diff_text, 0) + 1

        context_parts.append("【风险分布统计】")
        context_parts.append(f"- 高风险：{risk_levels.get('high', 0)} 份")
        context_parts.append(f"- 中风险：{risk_levels.get('medium', 0)} 份")
        context_parts.append(f"- 低风险：{risk_levels.get('low', 0)} 份")
        context_parts.append("")

        context_parts.append("【供应商出现频次】")
        sorted_vendors = sorted(vendor_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
        for vendor, stats in sorted_vendors:
            high_risk_count = stats["risk_levels"].count("high")
            context_parts.append(f"- {vendor}：{stats['count']} 次合同审查")
        context_parts.append("")

        context_parts.append("【高频差异/风险点】")
        sorted_issues = sorted(common_issues.items(), key=lambda x: x[1], reverse=True)[:5]
        for issue, count in sorted_issues:
            context_parts.append(f"- 出现 {count} 次：{issue[:80]}...")
        context_parts.append("")

        context_parts.append("【合同元数据摘要】")
        for i, task in enumerate(tasks[:5], 1):
            if not task.result:
                continue
            result = task.result
            bid_info = result.get("bid_info", {})
            contract_info = result.get("contract_info", {})
            comparison = result.get("comparison", {})

            vendor = bid_info.get("vendor_name", "未知")
            amount = contract_info.get("total_amount", bid_info.get("total_amount", "未知"))
            date_str = task.created_at.strftime("%Y-%m-%d") if task.created_at else "未知"

            context_parts.append(
                f"{i}. {date_str} | 供应商：{vendor} | 金额：{amount} | "
                f"风险：{comparison.get('risk_level', '未知')} | "
                f"结论：{comparison.get('conclusion', '无')[:50]}..."
            )

        return "\n".join(context_parts)

    async def generate_insights(self, tasks: List[TaskRecord]) -> List[Dict[str, str]]:
        """
        调用 LLM 生成宏观洞察
        """
        if not tasks:
            return [
                {
                    "type": "info",
                    "tag": "数据不足",
                    "content": "暂无足够的合同数据进行宏观分析，请完成更多比对任务。",
                    "action_text": "开始新的比对",
                }
            ]

        context = self._build_insights_context(tasks)

        prompt = f"""你作为银行首席审计官，基于以下真实的合同审查数据进行宏观分析。

{context}

请深度分析以上数据，识别出 4-5 条最具商业价值的宏观规律或风险信号。
要求：
1. 必须引用真实的供应商名称或具体日期，禁止套话
2. 分析要有数据支撑，指出具体的问题模式
3. 给出 1 条可操作的管理建议

以 JSON 对象格式返回，顶层字段为 "insights"，其值为洞察数组。每个洞察包含以下字段：
- type: "danger" 或 "info"（danger 表示高风险信号，info 表示一般洞察）
- tag: 简短的标签，如 "供应商集中度风险"、"付款条款异常"
- content: 具体的洞察内容，100-150字，必须包含真实数据点
- action_text: 建议的行动文本，如 "审查供应商资质"、"加强付款审核"

示例输出格式：
{{
  "insights": [
    {{
      "type": "danger",
      "tag": "供应商集中度风险",
      "content": "智科信息科技在过去30天内出现5次合同审查，占比达25%，且其中2份被标记为高风险。建议评估该供应商的集中度风险。",
      "action_text": "启动供应商风险评估"
    }}
  ]
}}
"""

        try:
            messages = [
                {"role": "system", "content": "你是一个专业的银行合同审计专家，擅长从数据中发现商业风险规律。输出必须是合法的 JSON 数组格式，不要包含任何其他文字。"},
                {"role": "user", "content": prompt},
            ]

            json_str, _ = await chat_completion(
                messages,
                response_format={"type": "json_object"},
            )

            content = json_str.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            insights = json.loads(content)
            if isinstance(insights, list):
                return insights[:5]
            elif isinstance(insights, dict) and "insights" in insights:
                return insights["insights"][:5]
            else:
                return [insights] if isinstance(insights, dict) else []

        except json.JSONDecodeError as e:
            return [
                {
                    "type": "info",
                    "tag": "分析生成中",
                    "content": "基于近期合同数据的宏观分析正在生成，建议稍后查看详细报告。",
                    "action_text": "刷新数据",
                }
            ]
        except Exception as e:
            return [
                {
                    "type": "danger",
                    "tag": "分析异常",
                    "content": f"洞察生成服务暂时不可用，错误：{str(e)[:50]}",
                    "action_text": "联系管理员",
                }
            ]


class InsightService:
    """AI 洞察持久化服务：管理洞察的获取和刷新"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.dashboard_service = DashboardService(db)

    async def get_latest_insights(self) -> Dict[str, Any]:
        """
        获取最新的 AI 洞察。
        如果没有记录，返回空数组。
        """
        from app.models.models import AiInsight

        result = await self.db.execute(
            select(AiInsight)
            .order_by(desc(AiInsight.updated_at))
            .limit(1)
        )
        record = result.scalar_one_or_none()

        if not record:
            return {
                "insights": [],
                "sample_count": 0,
                "generated_at": None,
                "is_fresh": False,
            }

        return {
            "insights": record.insights if record.insights else [],
            "sample_count": record.sample_count,
            "generated_at": record.updated_at.isoformat() if record.updated_at else None,
            "is_fresh": True,
        }

    async def refresh_insights(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        刷新 AI 洞察：
        1. 获取最新合同数据
        2. 调用 LLM 生成洞察
        3. 持久化到数据库
        4. 返回最新数据
        """
        from app.models.models import AiInsight
        import uuid

        # 1. 获取最近20条任务数据
        recent_tasks = await self.dashboard_service.get_recent_tasks(limit=20)

        # 2. 调用 LLM 生成洞察
        insights_raw = await self.dashboard_service.generate_insights(recent_tasks)

        # 3. 查询是否已有记录
        result = await self.db.execute(
            select(AiInsight).order_by(desc(AiInsight.updated_at)).limit(1)
        )
        existing_record = result.scalar_one_or_none()

        now = utc_now()

        # 游客不存在于 users 表，外键约束会报错，设为 None
        db_user_id = user_id if user_id and user_id != "guest" else None

        if existing_record:
            # 更新现有记录
            existing_record.insights = insights_raw
            existing_record.sample_count = len(recent_tasks)
            existing_record.generated_by = db_user_id
            existing_record.updated_at = now
        else:
            # 创建新记录
            new_record = AiInsight(
                id=str(uuid.uuid4()),
                insights=insights_raw,
                sample_count=len(recent_tasks),
                generated_by=db_user_id,
                created_at=now,
                updated_at=now,
            )
            self.db.add(new_record)

        await self.db.commit()

        return {
            "insights": insights_raw,
            "sample_count": len(recent_tasks),
            "generated_at": now.isoformat(),
            "is_fresh": True,
        }


class CopilotService:
    """Copilot 上下文感知服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_context(self) -> Dict[str, Any]:
        """Dashboard 页面的 Copilot 上下文"""
        from app.crud.crud_task import count_tasks

        today_new = await count_tasks(self.db, today_only=True)
        high_risk_count = await count_tasks(self.db, status="completed", is_high_risk=True)
        total_count = await count_tasks(self.db)

        # 获取最近检测的一份文件信息
        recent_task = await self._get_recent_task()

        greeting = "您好！我是您的合同审查助手。"

        if recent_task:
            context_summary = f"系统已累计检测 {total_count} 份合同。最近检测的是「{recent_task.get('project_name', '未知项目')}」，风险等级标记为 {recent_task.get('risk_level', '未知')}。"
        else:
            context_summary = f"系统已累计检测 {total_count} 份合同。今日新增 {today_new} 份审查，其中 {high_risk_count} 份被标记为高风险。"

        suggestions = [
            {"text": "最近检测的文件有什么风险？", "action": "latest_risk"},
            {"text": "系统累计检测了多少份合同？", "action": "total_count"},
            {"text": "今日有哪些高风险合同？", "action": "filter_risk"},
        ]

        return {
            "greeting": greeting,
            "context_summary": context_summary,
            "suggestions": suggestions,
        }

    async def _get_recent_task(self) -> Optional[Dict[str, Any]]:
        """获取最近一份检测任务的信息"""
        result = await self.db.execute(
            select(TaskRecord)
            .where(TaskRecord.status == "completed")
            .order_by(desc(TaskRecord.created_at))
            .limit(1)
        )
        task = result.scalar_one_or_none()

        if not task:
            return None

        comparison = (task.result or {}).get("comparison", {})
        bid_info = (task.result or {}).get("bid_info", {})
        contract_info = (task.result or {}).get("contract_info", {})

        # 使用文件名作为项目名称
        project_name = task.file_b_name or task.file_a_name or "未命名项目"

        return {
            "id": task.id,
            "project_name": project_name,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "risk_level": comparison.get("risk_level", "未知"),
            "conclusion": comparison.get("conclusion", "")[:100],
            "vendor_name": bid_info.get("vendor_name") or contract_info.get("vendor_name", "未知"),
            "amount": bid_info.get("total_amount") or contract_info.get("total_amount", "未知"),
        }

    async def get_compare_context(self, task_id: str) -> Dict[str, Any]:
        """比对详情页的 Copilot 上下文"""
        from app.crud.crud_task import get_task_db

        task = await get_task_db(self.db, task_id)
        if not task or not task.result:
            return {
                "greeting": "未找到该合同的比对结果。",
                "context_summary": "请等待任务完成后再进行询问。",
                "suggestions": [
                    {"text": "查看任务状态", "action": "check_status"},
                ],
            }

        result = task.result
        comparison = result.get("comparison", {})
        risk_level = comparison.get("risk_level", "未知")
        conclusion = comparison.get("conclusion", "")

        bid_info = result.get("bid_info", {})
        contract_info = result.get("contract_info", {})
        vendor = bid_info.get("vendor_name", contract_info.get("vendor_name", "未知"))

        comparison = result.get("comparison", {})
        diff_count = len(comparison.get("differences") or []) + len(
            comparison.get("missing_items") or []
        )
        greeting = f"合同审查结果：风险等级 {risk_level}，涉及供应商「{vendor}」，共发现 {diff_count} 处差异。"
        context_summary = f"比对结论摘要：{conclusion[:80]}... 您可以进一步询问违约金推演、差异对比或整改函生成。"

        suggestions = [
            {"text": "推演该合同违约金风险", "action": "simulate_penalty"},
            {"text": "对比采招与合同的关键差异", "action": "show_diff"},
            {"text": "生成整改建议函", "action": "generate_rectification"},
        ]

        return {
            "greeting": greeting,
            "context_summary": context_summary,
            "suggestions": suggestions,
        }

    async def get_records_context(self) -> Dict[str, Any]:
        """记录列表页的 Copilot 上下文"""
        return {
            "greeting": "这里是您的合同审查档案。",
            "context_summary": "您可以搜索历史记录、导出报表或查看详情。",
            "suggestions": [
                {"text": "如何导出Excel报表？", "action": "export_help"},
                {"text": "筛选本月的高风险合同", "action": "filter_month_risk"},
                {"text": "显示待归档的合同", "action": "show_pending_archive"},
            ],
        }

    async def get_context(self, page_id: str, item_id: Optional[str] = None) -> Dict[str, Any]:
        """
        根据页面 ID 获取对应的上下文

        Args:
            page_id: 页面标识，如 dashboard, compare, records, audit
            item_id: 可选的项目ID，如合同ID
        """
        if page_id == "dashboard":
            return await self.get_dashboard_context()
        elif page_id == "compare":
            return await self.get_compare_context(item_id or "")
        elif page_id in ("records", "audit", "personal"):
            return await self.get_records_context()
        else:
            return {
                "greeting": "您好！我是您的合同审查助手。",
                "context_summary": "有什么可以帮助您的吗？",
                "suggestions": [
                    {"text": "如何开始新的比对？", "action": "help_compare"},
                    {"text": "查看系统使用指南", "action": "help_guide"},
                ],
            }
