from typing import List, Optional
from pydantic import BaseModel, Field


class StatsData(BaseModel):
    total_reviews: int
    today_new: int
    high_risk_ratio: float
    avg_duration_seconds: float


class TrendData(BaseModel):
    dates: List[str]
    totals: List[int]
    risks: List[int]


class PieDataItem(BaseModel):
    name: str
    value: int


class RadarIndicator(BaseModel):
    name: str
    max: int


class RadarSeriesData(BaseModel):
    value: List[float]
    name: str


class RadarChartData(BaseModel):
    indicators: List[RadarIndicator]
    series: List[RadarSeriesData]


class DashboardStatsResponse(BaseModel):
    total_reviews: int
    today_new: int
    high_risk_ratio: float
    avg_duration_seconds: float
    radar: RadarChartData


class InsightItem(BaseModel):
    type: str = Field(..., description="类型: danger/info")
    tag: str = Field(..., description="标签")
    content: str = Field(..., description="洞察内容")
    action_text: str = Field(..., description="建议行动")


class DashboardInsightsResponse(BaseModel):
    insights: List[InsightItem]
    generated_at: str


class CopilotSuggestion(BaseModel):
    text: str
    action: Optional[str] = None


class CopilotContextResponse(BaseModel):
    page_id: str
    greeting: str
    context_summary: str
    suggestions: List[CopilotSuggestion]
