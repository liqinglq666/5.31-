from typing import Any, List, Optional
from pydantic import BaseModel


class BaseResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None


class StatsData(BaseModel):
    total_reviews: int
    today_new: int
    high_risk_ratio: float
    avg_duration_seconds: float


class StatsResponse(BaseResponse):
    data: StatsData


class RecordItem(BaseModel):
    task_id: str
    project_name: str
    created_at: Optional[str]
    status: str
    risk_level: str
    conclusion: str


class RecordsData(BaseModel):
    total: int
    page: int
    page_size: int
    list: List[RecordItem]


class RecordsResponse(BaseResponse):
    data: RecordsData


class TrendData(BaseModel):
    dates: List[str]
    totals: List[int]
    risks: List[int]


class TrendResponse(BaseResponse):
    data: TrendData


class PieDataItem(BaseModel):
    name: str
    value: int


class TaskStatusData(BaseModel):
    task_id: str
    status: str
    message: str
    progress: int
    result: Optional[Any]
    created_at: Optional[str]


class TaskStatusResponse(BaseResponse):
    data: TaskStatusData
