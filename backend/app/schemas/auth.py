from pydantic import BaseModel, Field


class RegisterPayload(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)
    full_name: str | None = None
    employee_id: str | None = None
    position: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
