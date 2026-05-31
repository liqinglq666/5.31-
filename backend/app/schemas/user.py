from typing import Optional
from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    employee_id: Optional[str] = None
    position: Optional[str] = None
    status: str
    is_admin: bool
    created_at: Optional[str] = None
    task_count: Optional[int] = None


class PendingUserResponse(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    employee_id: Optional[str] = None
    position: Optional[str] = None
    status: str
    created_at: Optional[str] = None


class UserToggleStatusResponse(BaseModel):
    user_id: str
    status: str
    message: str
