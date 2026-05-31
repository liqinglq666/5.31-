"""
services/memory_service.py
--------------------------
供应商画像与历史风险条款的数据库交互服务（MemoryService）。
使用 PostgreSQL + SQLAlchemy AsyncSession，零内存 Mock。
"""

import logging
import re
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.memory import SupplierProfile, HistoricalRiskClause
from app.infrastructure.llm.client import create_openai_client, _resolve_api_model_id, get_default_model_id

logger = logging.getLogger(__name__)


class MemoryService:
    """
    记忆服务：管理供应商画像与历史风险条款的读写。
    所有查询直接命中 PostgreSQL，不保留任何内存缓存。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Task 1: 供应商画像查询
    # ------------------------------------------------------------------
    async def get_supplier_profile(self, supplier_name: str) -> str:
        """
        根据供应商名称查询画像。
        返回一段可直接嵌入 LLM Prompt 的结构化文本。
        """
        if not supplier_name or supplier_name.strip() in (
            "未知",
            "未命名项目",
            "",
            "无",
        ):
            return "该供应商为首次审查，暂无历史画像。"

        result = await self.db.execute(
            select(SupplierProfile).where(
                SupplierProfile.supplier_name == supplier_name.strip()
            )
        )
        profile: Optional[SupplierProfile] = result.scalar_one_or_none()

        if not profile:
            return "该供应商为首次审查，暂无历史画像。"

        clauses = profile.frequent_missing_clauses or []
        clauses_text = ""

        # 过滤双向未提及的通用伪缺失条款，并精简过长描述
        def _is_bidirectional_empty_clause(text: str) -> bool:
            """判断是否为双向未提及的通用条款（如保密、知识产权、不可抗力）。"""
            if not text:
                return True
            return any(kw in text for kw in ["保密协议", "知识产权", "不可抗力", "争议解决", "管辖法院"])

        def _compact_clause(text: str) -> str:
            """将长条款描述精简为关键词摘要。"""
            if not text:
                return ""
            # 去除位置标记
            text = re.sub(r"【[^】]+】", "", text).strip()
            # 去掉常见前缀后缀
            text = text.replace("采购结果中要求", "").replace("而合同中未提及", "").strip()
            # 提取顿号分隔的服务/物品关键词
            if "、" in text:
                parts = [p.strip() for p in text.split("、")]
                keywords = []
                for p in parts:
                    p = re.sub(r"（[^）]+）", "", p)
                    p = re.sub(r"\([^)]+\)", "", p)
                    p = re.sub(r"^(提供|要求|包含|含|每场|每次|每人|每个)", "", p).strip()
                    if p and len(p) < 12:
                        keywords.append(p)
                if keywords:
                    return "、".join(keywords)
            return text[:25] + "..." if len(text) > 25 else text

        if isinstance(clauses, list) and clauses:
            filtered = [
                _compact_clause(str(c))
                for c in clauses[:10]
                if not _is_bidirectional_empty_clause(str(c))
            ]
            clauses_text = "、".join(filtered)
        elif isinstance(clauses, dict) and clauses:
            sorted_items = sorted(
                clauses.items(), key=lambda x: x[1], reverse=True
            )[:5]
            filtered = [
                (k, v) for k, v in sorted_items
                if not _is_bidirectional_empty_clause(k)
            ]
            clauses_text = "、".join(f"{_compact_clause(k)}({v}次)" for k, v in filtered)

        summary = profile.risk_summary or "暂无总结"
        # 去重并精简重复总结句
        summary = re.sub(
            r"该供应商在最新审查中被标记为高风险。\s*",
            "",
            summary,
        ).strip()
        if summary:
            summary = f"画像总结：{summary}"

        return (
            f"历史共审查 {profile.total_contracts} 份合同，"
            f"高频不一致：{clauses_text or '无'}。{summary}"
        )

    # ------------------------------------------------------------------
    # Task 2: 历史风险条款轻量 RAG
    # ------------------------------------------------------------------
    async def search_similar_risk_clauses(
        self, text_content: str, limit: int = 5
    ) -> List[HistoricalRiskClause]:
        """
        基于关键词 ILIKE 匹配，从历史风险条款库中检索相似高风险案例。
        轻量级方案：无需向量数据库，直接利用 PostgreSQL 字符串匹配。
        """
        if not text_content or not text_content.strip():
            return []

        # 取前 300 字符作为查询源，避免全文过长导致关键词噪声
        query_text = text_content.strip()[:300]

        # 提取中文词（>=2 字）和英文词（>=3 字母）作为关键词
        words = re.findall(r"[一-龥]{2,}|[a-zA-Z]{3,}", query_text)
        # 去重，限制最多 10 个关键词防止查询膨胀
        words = list(dict.fromkeys(words))[:10]

        if not words:
            return []

        # 构建 OR ILIKE 条件
        conditions = [
            HistoricalRiskClause.original_text.ilike(f"%{w}%") for w in words
        ]

        stmt = (
            select(HistoricalRiskClause)
            .where(or_(*conditions))
            .where(
                HistoricalRiskClause.risk_level.in_(["high", "medium"])
            )
            .order_by(HistoricalRiskClause.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def format_rag_context(self, clauses: List[HistoricalRiskClause]) -> str:
        """
        将检索到的历史风险条款格式化为可直接注入 Prompt 的文本。
        """
        if not clauses:
            return "暂无相似历史风险条款记录。"

        lines = ["【历史相似风险条款】"]
        for c in clauses:
            lines.append(
                f"- [{c.risk_level or '未知'}] {c.clause_type or '未分类'}："
                f"{c.original_text[:120]}..."
            )
            if c.suggested_amendment:
                lines.append(
                    f"  建议修改：{c.suggested_amendment[:120]}..."
                )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Bonus: 从比对结果更新/创建供应商画像（记忆积累）
    # ------------------------------------------------------------------
    async def upsert_supplier_profile(
        self,
        supplier_name: str,
        new_missing_clauses: List[str],
        risk_level: str,
    ) -> None:
        """
        每次审查完成后，将本次发现的缺失条款回写到供应商画像，
        实现真正的记忆积累与自进化。
        注意：本方法不执行 commit，由调用方控制事务边界。
        """
        if not supplier_name or supplier_name.strip() in (
            "未知",
            "未命名项目",
            "",
            "无",
        ):
            return

        result = await self.db.execute(
            select(SupplierProfile).where(
                SupplierProfile.supplier_name == supplier_name.strip()
            )
        )
        profile: Optional[SupplierProfile] = result.scalar_one_or_none()

        if not profile:
            profile = SupplierProfile(
                supplier_name=supplier_name.strip(),
                total_contracts=1,
                frequent_missing_clauses=new_missing_clauses,
                risk_summary="",
            )
            self.db.add(profile)
        else:
            # 更新计数
            profile.total_contracts = (profile.total_contracts or 0) + 1

            # 合并高频缺失条款（支持 list 或 dict 格式）
            current = profile.frequent_missing_clauses or []
            if isinstance(current, list):
                merged = list(current)
                for clause in new_missing_clauses:
                    if clause and clause not in merged:
                        merged.append(clause)
                profile.frequent_missing_clauses = merged
            elif isinstance(current, dict):
                merged = dict(current)
                for clause in new_missing_clauses:
                    if clause:
                        merged[clause] = merged.get(clause, 0) + 1
                profile.frequent_missing_clauses = merged

        # 调用 LLM 生成供应商画像总结（新供应商和已有供应商都需要）
        try:
            summary = await _generate_supplier_summary(
                supplier_name,
                profile.total_contracts or 0,
                profile.frequent_missing_clauses,
                risk_level,
            )
            # 如果 LLM 返回空内容，使用 fallback
            if not summary or not summary.strip():
                logger.warning("[MemoryService] LLM 返回空总结，使用 fallback")
                raise ValueError("LLM 返回空内容")
            profile.risk_summary = summary
            logger.info("[MemoryService] 供应商 '%s' 画像总结生成成功: %s", supplier_name, summary[:50])
        except Exception as exc:
            logger.warning("[MemoryService] LLM 生成画像总结失败: %s", exc)
            # fallback 到固定文本
            if risk_level == "high":
                profile.risk_summary = "最新审查标记为高风险。"
            elif risk_level == "medium":
                profile.risk_summary = "最新审查标记为中风险。"
            else:
                profile.risk_summary = "最新审查标记为低风险。"


async def _generate_supplier_summary(
    supplier_name: str,
    total_contracts: int,
    frequent_missing_clauses: list | dict,
    risk_level: str,
) -> str:
    """调用 LLM 生成供应商画像总结。"""
    client = create_openai_client()
    model_id = _resolve_api_model_id(get_default_model_id())

    # 格式化缺失条款
    clauses_text = ""
    if isinstance(frequent_missing_clauses, list) and frequent_missing_clauses:
        clauses_text = "、".join(str(c) for c in frequent_missing_clauses[:10])
    elif isinstance(frequent_missing_clauses, dict) and frequent_missing_clauses:
        sorted_items = sorted(frequent_missing_clauses.items(), key=lambda x: x[1], reverse=True)[:5]
        clauses_text = "、".join(f"{k}({v}次)" for k, v in sorted_items)
    else:
        clauses_text = "暂无"

    prompt = f"""你是一位资深银行法务审计专家，负责为供应商建立动态风险画像。

【已知数据】
- 供应商名称：{supplier_name}
- 累计审查合同数：{total_contracts}
- 历史高频缺失条款：{clauses_text}
- 最新风险等级：{risk_level}

【输出要求】
生成一段 60-100 字的专业画像总结，包含：
1. 风险趋势判断（恶化/稳定/改善）
2. 高频问题根因
3. 后续合作风控建议

语气专业、客观、可执行。不要套话。直接输出总结文本，不要加标题。"""

    response = await client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": "你是一位银行法务审计专家，擅长供应商风险评估。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=200,
    )
    content = response.choices[0].message.content
    if content is None:
        logger.warning("[MemoryService] LLM 返回 content 为 None")
        raise ValueError("LLM 返回 content 为 None")
    result = content.strip()
    logger.info("[MemoryService] LLM 返回供应商总结: %s", result[:80])
    return result
