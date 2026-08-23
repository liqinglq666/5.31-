"""
core/redis_client.py
--------------------
Redis 连接管理器（单例模式）。
用于在线用户追踪、缓存等轻量级场景。
"""

import redis.asyncio as aioredis
from app.core.config import settings

_redis_pool = None


async def get_redis():
    """获取 Redis 异步连接（单例）。"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_pool
