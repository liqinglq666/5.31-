"""
infrastructure/llm/dynamic_config.py
------------------------------------
模型动态配置层：数据库驱动的 LLM 配置管理。

职责：
1. 从数据库加载 SysModelConfig 到全局内存缓存，避免每次 LLM 调用都查库。
2. Fernet 解密加密存储的 API Key。
3. 提供 Admin API 触发的缓存刷新接口。

安全设计：
- 数据库只存密文 API Key。
- 解密盐 DB_ENCRYPTION_KEY 仅存于服务器环境变量，不落地代码。
- Admin 列表接口返回脱敏后的 API Key。
"""

import logging
from typing import Dict, Optional

from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.models import SysModelConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 全局内存缓存
# ---------------------------------------------------------------------------
_model_config_cache: Dict[str, dict] = {}
_active_model_cache: Optional[dict] = None

# ---------------------------------------------------------------------------
# Fernet 解密器初始化
# ---------------------------------------------------------------------------
cipher_suite: Optional[Fernet] = None
if settings.db_encryption_key:
    try:
        cipher_suite = Fernet(settings.db_encryption_key.encode())
    except Exception as exc:
        logger.warning("[DynamicConfig] DB_ENCRYPTION_KEY 格式无效，无法初始化 Fernet: %s", exc)


def encrypt_api_key(plain_key: str) -> str:
    """加密明文 API Key，用于 Admin 写入数据库前调用。无密钥时直接存明文。"""
    if not cipher_suite:
        return plain_key
    return cipher_suite.encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    """解密数据库中存储的密文 API Key。"""
    if not cipher_suite:
        return encrypted
    return cipher_suite.decrypt(encrypted.encode()).decode()


def mask_api_key(key: str) -> str:
    """脱敏展示：sk-abcd******wxyz"""
    if len(key) <= 8:
        return "******"
    return f"{key[:4]}******{key[-4:]}"


# ---------------------------------------------------------------------------
# 缓存刷新（由 Admin API 在配置变更后调用）
# ---------------------------------------------------------------------------
async def refresh_model_config_cache():
    """异步从数据库全量刷新内存缓存。"""
    global _model_config_cache, _active_model_cache

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SysModelConfig))
        configs = result.scalars().all()

    new_cache: Dict[str, dict] = {}
    new_active: Optional[dict] = None

    for c in configs:
        try:
            api_key = decrypt_api_key(c.encrypted_api_key) if c.encrypted_api_key else ""
        except Exception as exc:
            logger.warning(
                "[DynamicConfig] 解密 model=%s 的 API Key 失败: %s", c.model_name, exc
            )
            api_key = ""

        cfg = {
            "id": c.id,
            "provider": c.provider,
            "model_name": c.model_name,
            "api_model_id": c.api_model_id or "",
            "base_url": c.base_url or "",
            "api_key": api_key,
            "temperature": c.temperature or "0.0",
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        new_cache[c.model_name] = cfg
        if c.is_active:
            new_active = cfg

    _model_config_cache = new_cache
    _active_model_cache = new_active
    logger.info(
        "[DynamicConfig] 缓存已刷新: %d 条配置, active=%s",
        len(new_cache),
        new_active["model_name"] if new_active else "None",
    )


# ---------------------------------------------------------------------------
# 同步读取接口（供 create_openai_client 等同步/异步函数调用）
# ---------------------------------------------------------------------------
def get_cached_model_config(model_name: str) -> Optional[dict]:
    """按 model_name 读取内存缓存中的动态配置。"""
    return _model_config_cache.get(model_name)


def get_cached_active_model() -> Optional[dict]:
    """读取当前被标记为 is_active=True 的动态配置。"""
    return _active_model_cache


def get_all_cached_models() -> list[dict]:
    """返回内存缓存中所有动态配置。"""
    return list(_model_config_cache.values())


def get_default_model_id() -> str:
    """获取当前应使用的默认模型 ID。
    优先级：数据库 active 配置 > settings.llm_model。
    """
    active = get_cached_active_model()
    if active:
        return active["model_name"]
    return settings.llm_model
