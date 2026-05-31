"""
auth_router.py
-------------
用户注册与登录接口。
"""

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    verify_password,
    create_access_token,
    get_current_user,
    create_guest_token,
)
from app.core.database import get_db
from app.core.exceptions import AuthError, ConflictError, PermissionDeniedError
from app.models.models import User
from app.crud.crud_user import get_user_by_username, create_user
from app.schemas.auth import RegisterPayload, TokenResponse

router = APIRouter()


@router.post("/api/v1/auth/register")
async def register(payload: RegisterPayload, db: AsyncSession = Depends(get_db)):
    """用户注册，默认状态为 pending，需管理员审批后方可登录。"""
    existing = await get_user_by_username(db, payload.username)
    if existing:
        raise ConflictError("用户名已存在")

    user = await create_user(
        db,
        username=payload.username,
        password=payload.password,
        full_name=payload.full_name,
        employee_id=payload.employee_id,
        position=payload.position,
    )
    return {"code": 200, "message": "注册成功，等待管理员审批", "user_id": user.id}


@router.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """用户登录，验证账号密码及 active 状态，成功后返回 JWT。"""
    user = await get_user_by_username(db, form_data.username)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise AuthError("用户名或密码错误")

    if user.status != "active":
        raise PermissionDeniedError("用户账号未激活，请联系管理员")

    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/api/v1/auth/guest")
async def guest_login():
    """游客登录，返回临时 JWT Token（2 小时过期）。"""
    access_token = create_guest_token()
    return {
        "code": 200,
        "message": "游客登录成功",
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get("/api/v1/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户详细信息。"""
    return {
        "code": 200,
        "message": "查询成功",
        "data": {
            "id": current_user.id,
            "username": current_user.username,
            "full_name": current_user.full_name,
            "employee_id": current_user.employee_id,
            "position": current_user.position,
            "is_admin": current_user.is_admin,
            "status": current_user.status,
        },
    }
