"""
api/v1/endpoints/system.py
--------------------------
系统级接口：模型可用性查询、当前激活模型查询等。
"""

from fastapi import APIRouter, Request

from app.core.redis_client import get_redis
from app.core.security import decode_token
from app.infrastructure.llm.dynamic_config import (
    get_all_cached_models,
    get_cached_active_model,
)

router = APIRouter()


@router.get("/api/v1/system/models")
async def get_available_models():
    """
    返回当前数据库中已配置 API Key 的可用模型列表。
    不再 fallback 到硬编码注册表，完全由管理员在后台控制。
    """
    available = []
    for db_cfg in get_all_cached_models():
        if db_cfg.get("api_key"):
            available.append({
                "id": db_cfg["model_name"],
                "name": db_cfg["model_name"],
                "provider": db_cfg["provider"],
                "base_url": db_cfg.get("base_url", ""),
                "temperature": db_cfg.get("temperature", "0.0"),
                "source": "database",
            })
    return {"code": 200, "data": available}


@router.get("/api/v1/system/active_model")
async def get_active_model():
    """
    返回当前系统正在使用的激活模型信息（供前端 Badge 展示）。
    仅从数据库动态配置中读取，无 fallback。
    """
    active = get_cached_active_model()
    if active:
        return {
            "code": 200,
            "data": {
                "model_name": active["model_name"],
                "provider": active["provider"],
                "base_url": active.get("base_url", ""),
                "temperature": active.get("temperature", "0.0"),
            },
        }
    return {
        "code": 200,
        "data": None,
        "message": "管理员尚未配置激活模型",
    }


@router.get("/api/v1/system/online")
async def get_online_count(request: Request):
    """
    返回当前在线用户人数。
    基于 Redis 中未过期的 `online:*` key 统计。
    若请求携带游客 token，也将游客计入在线人数。
    """
    try:
        redis = await get_redis()
        keys = await redis.keys("online:*")
        count = len(keys)

        # 检查是否是游客 token，如果是则确保计入
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            payload = decode_token(token)
            if payload and payload.get("is_guest") and payload.get("sub") == "guest":
                # 游客也写入在线标记并计入
                await redis.setex("online:guest", 300, "1")
                keys = await redis.keys("online:*")
                count = len(keys)

        return {"code": 200, "data": {"count": count}}
    except Exception:
        return {"code": 200, "data": {"count": 0}}
