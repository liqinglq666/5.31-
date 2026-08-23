from typing import Optional, List, Any
from pydantic import BaseModel, Field


class CompareRules(BaseModel):
    """可配置比对规则，随比对任务一同提交"""

    price_tolerance: float = Field(0.0, ge=0.0, description="金额容差百分比，如 5.0 表示 +-5%")
    required_clauses: List[str] = Field(default_factory=list, description="必检条款名称清单")
    custom_requirements: str = Field("", description="用户自定义的额外审查要求或输出格式要求")


class TaskCreateResponse(BaseModel):
    task_id: str
    status: str


class TaskStatusData(BaseModel):
    task_id: str
    status: str
    message: str
    progress: int
    result: Optional[Any] = None
    process_mode: Optional[str] = None
    created_at: Optional[str] = None
    creator_name: Optional[str] = None
    creator_emp_id: Optional[str] = None


class RecordItem(BaseModel):
    task_id: str
    project_name: str
    created_at: Optional[str] = None
    status: str
    risk_level: str
    conclusion: str
    creator_id: Optional[str] = None
    creator_name: Optional[str] = None
    creator_emp_id: Optional[str] = None


class RecordsData(BaseModel):
    total: int
    page: int
    page_size: int
    list: List[RecordItem]


class TaskArchiveResponse(BaseModel):
    task_id: str
    archive_time: Optional[str] = None


class HistoryItem(BaseModel):
    task_id: str
    file_a_name: Optional[str] = None
    file_b_name: Optional[str] = None
    status: str
    message: str
    progress: int
    result: Optional[Any] = None
    created_at: Optional[str] = None


class RemarkRequest(BaseModel):
    """任务备注请求体"""

    remark: str


class DifferenceItemSchema(BaseModel):
    """差异项 Schema，包含原文锚点与风险注释"""

    description: str = Field(..., description="差异描述")
    suggested_amendment: str = Field(default="", description="法务起草的修改建议条款")
    original_text: str = Field(
        default="",
        description="采购结果文件中的原句，一字不差摘录，用于前端高亮锚点匹配",
    )
    contract_text: str = Field(
        default="",
        description="正式合同文件中的原句，一字不差摘录，用于前端高亮锚点匹配",
    )
    risk_comment: str = Field(
        default="",
        description="AI 针对本条差异生成的风险注释与审查意见",
    )
    is_favorable_to_buyer: bool = Field(
        default=False,
        description="如果该差异对采购方/我方绝对有利，设为 true",
    )


class MissingItemSchema(BaseModel):
    """缺失项 Schema，包含原文锚点与风险注释"""

    clause_name: str = Field(default="", description="缺失条款名称，如'增值服务'、'保密协议'")
    description: str = Field(..., description="缺失条款描述")
    suggested_amendment: str = Field(..., description="法务起草的补充条款")
    original_text: str = Field(
        default="",
        description="采购结果文件中的原句，一字不差摘录",
    )
    contract_text: str = Field(
        default="",
        description="合同原文中本条款应出现位置的上下文原句，用于前端高亮锚点匹配",
    )
    risk_comment: str = Field(
        default="",
        description="AI 针对本条缺失生成的风险注释与审查意见",
    )


class CompareResultSchema(BaseModel):
    """比对结果 Schema（由三 Agent 接力产出）"""

    risk_level: str = Field(..., description="风险等级：high / medium / low")
    confidence_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="风控总管评定的全局置信度 0~1"
    )
    differences: List[DifferenceItemSchema] = Field(
        default_factory=list, description="差异详情列表（含原文锚点与修改建议）"
    )
    missing_items: List[MissingItemSchema] = Field(
        default_factory=list, description="缺失条款列表（含原文锚点与补充建议）"
    )
    matches: List[str] = Field(default_factory=list, description="一致项详情列表")
    parsed_contract_text: str = Field(
        default="",
        description="解析后的最终合同纯文本，供前端左右双屏原文高亮使用",
    )
    agent_traces: List[Any] = Field(
        default_factory=list, description="多智能体协作轨迹记录"
    )
    token_usage: dict = Field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        description="多智能体协作总 Token 消耗统计",
    )


class MemoryContext(BaseModel):
    """比对任务返回的双重记忆上下文（供应商画像 + 历史风险条款）"""

    supplier_context: str = Field(
        "", description="供应商宏观画像文本，可直接注入 LLM Prompt"
    )
    rag_context: str = Field(
        "", description="相似历史风险条款预警文本，可直接注入 LLM Prompt"
    )
