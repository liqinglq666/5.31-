"""
models/memory.py
---------------
供应商画像与历史风险条款的 SQLAlchemy ORM 模型。
"""

import uuid

from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base
from app.models.models import utc_now


class SupplierProfile(Base):
    """供应商画像：累积审查数据，形成供应商级风险认知"""
    __tablename__ = "supplier_profiles"

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
        comment="全局唯一画像 ID（UUID）",
    )
    supplier_name = Column(
        String,
        nullable=False,
        unique=True,
        index=True,
        comment="供应商名称（唯一索引）",
    )
    total_contracts = Column(
        Integer,
        default=0,
        comment="累计审查合同数量",
    )
    frequent_missing_clauses = Column(
        JSONB,
        default=list,
        comment="常漏条款统计（JSONB，如 ['保密协议', '知识产权'] 或 {'保密协议': 3}）",
    )
    risk_summary = Column(
        Text,
        nullable=True,
        comment="AI 生成的供应商画像总结",
    )
    created_at = Column(DateTime, default=utc_now, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        comment="更新时间",
    )


class HistoricalRiskClause(Base):
    """历史风险条款库：沉淀每次审查中发现的高风险条款，用于相似预警"""
    __tablename__ = "historical_risk_clauses"

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
        comment="全局唯一条款 ID（UUID）",
    )
    clause_type = Column(
        String,
        nullable=True,
        index=True,
        comment="条款类型，如付款条款、违约责任、交付周期",
    )
    original_text = Column(
        Text,
        nullable=False,
        comment="风险条款原文（合同中的原始表述）",
    )
    risk_level = Column(
        String,
        nullable=True,
        comment="风险等级：high / medium / low",
    )
    suggested_amendment = Column(
        Text,
        nullable=True,
        comment="法务建议的修改/补充条款",
    )
    created_at = Column(DateTime, default=utc_now, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        comment="更新时间",
    )
