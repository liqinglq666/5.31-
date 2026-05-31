"""
models/models.py
---------------
SQLAlchemy ORM 模型定义：User、TaskRecord。
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


def utc_now() -> datetime:
    """返回当前 UTC 时间（naive datetime，与 PostgreSQL timestamp without time zone 兼容）。"""
    return datetime.utcnow()


class User(Base):
    """用户 ORM 模型，存储系统人员信息"""
    __tablename__ = "users"

    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
        comment="全局唯一用户 ID（UUID）",
    )
    username = Column(String, unique=True, nullable=False, comment="登录用户名")
    password_hash = Column(String, nullable=False, comment="密码哈希")
    full_name = Column(String, nullable=True, comment="姓名")
    employee_id = Column(String, nullable=True, comment="工号")
    position = Column(String, nullable=True, comment="职务")
    status = Column(String, default="pending", comment="用户状态: pending / active")
    is_admin = Column(Boolean, default=False, comment="是否为管理员")
    created_at = Column(DateTime, default=utc_now, comment="创建时间")

    tasks = relationship("TaskRecord", back_populates="reviewer", foreign_keys="TaskRecord.reviewer_id")
    created_tasks = relationship("TaskRecord", back_populates="creator", foreign_keys="TaskRecord.creator_id")


class TaskRecord(Base):
    """任务记录 ORM 模型，持久化存储在 PostgreSQL 中"""
    __tablename__ = "task_records"

    id = Column(String, primary_key=True, index=True, comment="全局唯一任务 ID（UUID）")
    file_a_name = Column(String, nullable=True, comment="采购结果文件名")
    file_b_name = Column(String, nullable=True, comment="合同文件名")
    status = Column(String, default="pending", comment="任务状态")
    progress = Column(Integer, default=0, comment="处理进度 0-100")
    message = Column(String, default="任务已创建，等待执行", comment="当前状态描述")
    result = Column(JSON, nullable=True, comment="任务执行结果")
    created_at = Column(DateTime, default=utc_now, comment="创建时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    creator_id = Column(String, ForeignKey("users.id"), nullable=True, comment="创建人ID")
    reviewer_id = Column(String, ForeignKey("users.id"), nullable=True, comment="审查员ID")
    archive_time = Column(DateTime, nullable=True, comment="归档时间")
    is_archived = Column(Boolean, default=False, comment="是否已归档")
    supplier_name = Column(String, nullable=True, index=True, comment="供应商名称（从比对结果中提取）")
    process_mode = Column(String, nullable=True, default="DIRECT", comment="处理模式: DIRECT / RAG")
    model_name = Column(String(100), nullable=True, comment="执行该任务时使用的底层大模型名称")
    processing_seconds = Column(Integer, nullable=True, comment="任务实际执行耗时（秒）")
    remark = Column(String, nullable=True, comment="备注信息")
    remark_time = Column(DateTime, nullable=True, comment="备注时间")
    remark_reviewer_id = Column(String, ForeignKey("users.id"), nullable=True, comment="备注人ID")
    remark_reviewer = relationship("User", foreign_keys=[remark_reviewer_id])

    creator = relationship("User", back_populates="created_tasks", foreign_keys=[creator_id])
    reviewer = relationship("User", back_populates="tasks", foreign_keys=[reviewer_id])


class AiInsight(Base):
    """AI 洞察持久化表，存储宏观分析结果"""
    __tablename__ = "ai_insights"

    id = Column(String, primary_key=True, index=True, comment="全局唯一洞察 ID（UUID）")
    insights = Column(JSON, nullable=False, comment="AI 洞察内容（JSON 数组格式）")
    sample_count = Column(Integer, default=0, comment="生成时使用的样本数量")
    generated_by = Column(String, ForeignKey("users.id"), nullable=True, comment="触发生成的用户ID")
    created_at = Column(DateTime, default=utc_now, comment="创建时间")
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, comment="更新时间")


class SysModelConfig(Base):
    """系统大模型配置表：支持动态热切换与多模型管理。"""
    __tablename__ = "sys_model_configs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增主键")
    provider = Column(String(50), nullable=False, comment="服务商标识: openai / deepseek / qwen / zhipu 等")
    model_name = Column(String(100), nullable=False, unique=True, comment="模型显示名称（前端展示用）")
    api_model_id = Column(String(100), nullable=True, comment="API 实际调用时的模型 ID（如 deepseek-chat）")
    base_url = Column(String(255), nullable=True, comment="API BaseURL，适配代理或私有化部署")
    encrypted_api_key = Column(String(255), nullable=False, comment="Fernet 加密后的 API Key")
    temperature = Column(String(10), nullable=True, default="0.0", comment="模型采样温度，默认 0.0")
    is_active = Column(Boolean, default=False, comment="是否为当前激活模型（全局仅一条为 True）")
    created_at = Column(DateTime, default=utc_now, comment="创建时间")
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, comment="更新时间")
