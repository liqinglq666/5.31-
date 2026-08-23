"""
core/security.py
----------------
人员鉴权核心模块：
- 密码哈希与校验（bcrypt）
- JWT Access Token 生成与解析
- FastAPI 依赖注入：get_current_user / get_admin_user
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.models import User


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希值是否匹配。"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """生成 JWT Access Token，默认过期时间为 24 小时。"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            hours=settings.access_token_expire_hours
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.algorithm
    )
    return encoded_jwt


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    解析请求头中的 Bearer Token，返回当前登录用户对象。
    认证成功后，将用户标记为在线（Redis，5 分钟过期）。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账号未激活，请联系管理员",
        )

    # 在线追踪：写入 Redis，5 分钟过期
    try:
        redis = await get_redis()
        await redis.setex(f"online:{user_id}", 300, "1")
    except Exception:
        pass  # Redis 失败不影响认证

    return user


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    依赖 get_current_user，仅允许管理员访问。
    如果当前用户不是管理员，则抛出 403 异常。
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


# ---------------------------------------------------------------------------
# 游客模式
# ---------------------------------------------------------------------------

def create_guest_token() -> str:
    """生成游客 JWT Token，过期时间 2 小时。"""
    expire = datetime.now(timezone.utc) + timedelta(hours=2)
    to_encode = {"sub": "guest", "is_guest": True, "exp": expire}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[dict]:
    """解析 JWT Token，返回 payload 或 None。"""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        return None


async def get_current_user_or_guest(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    解析 Bearer Token，支持正常用户和游客。
    游客身份：sub='guest'，is_guest=True。
    返回一个特殊的 User 对象（id='guest'）。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    user_id: Optional[str] = payload.get("sub")
    is_guest = payload.get("is_guest", False)

    if is_guest and user_id == "guest":
        return User(
            id="guest",
            username="guest",
            full_name="游客",
            employee_id="",
            position="",
            is_admin=False,
            status="active",
            password_hash="",
        )

    if user_id is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账号未激活，请联系管理员",
        )

    # 在线追踪：写入 Redis，5 分钟过期
    try:
        redis = await get_redis()
        await redis.setex(f"online:{user_id}", 300, "1")
    except Exception:
        pass

    return user
