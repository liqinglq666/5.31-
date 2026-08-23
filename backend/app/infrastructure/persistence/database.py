"""
core/database.py
---------------
数据层基础设施：异步 PostgreSQL 引擎、Session 工厂与 FastAPI 依赖注入。
"""

import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.core.config import settings

logger = logging.getLogger(__name__)

POSTGRES_URL = settings.postgres_url
if POSTGRES_URL.startswith("postgresql://"):
    ASYNC_POSTGRES_URL = POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    ASYNC_POSTGRES_URL = POSTGRES_URL

async_engine = create_async_engine(ASYNC_POSTGRES_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# 同步 engine 仅用于 alembic 迁移等场景（保留兼容）
sync_engine = create_async_engine(ASYNC_POSTGRES_URL, pool_pre_ping=True)
Base = declarative_base()


async def init_db():
    """应用启动时自动建表。"""
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[Database] PostgreSQL 数据表初始化成功")
    except Exception as exc:
        logger.warning("[Database] PostgreSQL 连接或建表失败: %s", exc)


async def get_db():
    """FastAPI 依赖注入函数，为每个请求生成独立的 AsyncSession。"""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()


@asynccontextmanager
async def db_session():
    """供后台任务使用的异步数据库会话上下文管理器。"""
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()
