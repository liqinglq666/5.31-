from pydantic import BaseModel, Field


class ExportQuery(BaseModel):
    task_ids: str = Field(..., description="逗号分隔的任务 ID 列表")
