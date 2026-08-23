"""
兼容层：core/database.py → infrastructure/persistence/database.py
旧导入路径保持可用，新代码请使用 app.infrastructure.persistence.database
"""

from app.infrastructure.persistence.database import (
    Base,
    AsyncSessionLocal,
    async_engine,
    sync_engine,
    init_db,
    get_db,
    db_session,
)

# 向后兼容别名
engine = async_engine

__all__ = ["Base", "AsyncSessionLocal", "async_engine", "sync_engine", "engine", "init_db", "get_db", "db_session"]
