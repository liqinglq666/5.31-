"""
domain/contract/entities.py
---------------------------
合同领域实体与值对象。

核心业务模型：ContractInfo、ContractItem、BusinessMetric、DifferenceItem、
MissingItem、CompareResult、FinancialInfo、PaymentNode。
"""

import json
from typing import Any, Dict, List, Annotated

from pydantic import BaseModel, Field, BeforeValidator


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _coerce_unknown_to_zero(val: Any) -> Any:
    """将模型可能返回的 '未知' / '' / None 等非法数字统一转为 0。"""
    if isinstance(val, str):
        cleaned = val.strip()
        if cleaned in ("未知", "", "null", "None", "无"):
            return 0
        try:
            return float(cleaned)
        except ValueError:
            return 0
    if val is None:
        return 0
    return val


def _coerce_to_business_metric(val: Any) -> Any:
    """兼容 LLM 返回的旧格式（纯数字）与新格式（嵌套对象），统一包装为 BusinessMetric dict。"""
    if isinstance(val, dict):
        # 已经是新格式，透传给 Pydantic 解析
        return val
    if isinstance(val, (int, float)):
        return {"value": float(val), "reference": "原文未明确标明"}
    if isinstance(val, str):
        cleaned = val.strip()
        if cleaned in ("未知", "", "null", "None", "无"):
            return {"value": 0.0, "reference": "原文未明确标明"}
        try:
            num = float(cleaned)
            return {"value": num, "reference": "原文未明确标明"}
        except ValueError:
            return {"value": 0.0, "reference": "原文未明确标明"}
    if val is None:
        return {"value": 0.0, "reference": "原文未明确标明"}
    return val


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------

class BusinessMetric(BaseModel):
    """带精确条款出处的商务指标（值 + 位置锚点）。

    通过实现数字协议（__float__ / __int__ / __bool__ / __mul__ 等），
    使旧代码中大量存在的 float(x)、if x:、x * 0.3 等表达式无需改动即可兼容。
    """

    value: Annotated[float, BeforeValidator(_coerce_unknown_to_zero)] = Field(
        ..., description="提取出的确切数值。必须是纯数字，缺失填 0"
    )
    reference: str = Field(
        default="原文未明确标明",
        description="该数值在原文中的精确章节与条款号（如'第3条第2款'或'附件一'）"
    )

    def __float__(self) -> float:
        return float(self.value)

    def __int__(self) -> int:
        return int(self.value)

    def __bool__(self) -> bool:
        return bool(self.value)

    def __str__(self) -> str:
        return str(self.value)

    def __mul__(self, other: Any) -> float:
        if isinstance(other, BusinessMetric):
            return self.value * other.value
        return self.value * other

    def __rmul__(self, other: Any) -> float:
        return self.__mul__(other)

    def __truediv__(self, other: Any) -> float:
        if isinstance(other, BusinessMetric):
            return self.value / other.value
        return self.value / other

    def __add__(self, other: Any) -> float:
        if isinstance(other, BusinessMetric):
            return self.value + other.value
        return self.value + other

    def __sub__(self, other: Any) -> float:
        if isinstance(other, BusinessMetric):
            return self.value - other.value
        return self.value - other


def flatten_business_metrics(obj: Any) -> Any:
    """递归展平 BusinessMetric 对象。

    将后端内部使用的 {value, reference} 嵌套对象还原为纯数值，
    同时保留 reference 到同级字段（如 total_amount_reference），
    保证前端 API 兼容旧类型定义（number | string），无需改动前端代码。
    """
    if isinstance(obj, dict):
        if set(obj.keys()) == {"value", "reference"}:
            return obj["value"]
        result: Dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(v, dict) and set(v.keys()) == {"value", "reference"}:
                result[k] = v["value"]
                result[f"{k}_reference"] = v["reference"]
            else:
                result[k] = flatten_business_metrics(v)
        return result
    if isinstance(obj, list):
        return [flatten_business_metrics(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

class ContractItem(BaseModel):
    """采购明细项（品名、规格、数量、单价、位置）"""

    name: str = Field(..., description="品名/名称")
    specification: str = Field(default="", description="规格型号")
    quantity: Annotated[float, BeforeValidator(_coerce_unknown_to_zero)] = Field(
        0, description="数量，必须转换为纯数字，缺失时填 0"
    )
    unit_price: Annotated[float, BeforeValidator(_coerce_unknown_to_zero)] = Field(
        0, description="单价（元），必须转换为纯数字，缺失时填 0"
    )
    total_price: Annotated[float, BeforeValidator(_coerce_unknown_to_zero)] = Field(
        0, description="小计金额（元），必须转换为纯数字，缺失时填 0"
    )
    position: str = Field(
        default="", description="在原文中的位置描述，如'合同第1条采购明细第2项'"
    )


class ContractInfo(BaseModel):
    """从文本中提取出的合同关键信息"""

    vendor_name: str = Field(..., description="供应商名称")
    total_amount: Annotated[BusinessMetric, BeforeValidator(_coerce_to_business_metric)] = Field(
        ..., description="合同总金额（含条款出处）。value 单位：元；reference 为精确条款号"
    )
    delivery_days: Annotated[BusinessMetric, BeforeValidator(_coerce_to_business_metric)] = Field(
        ..., description="交期天数（含条款出处）。value 为整数天数；reference 为精确条款号"
    )
    delay_daily_rate: Annotated[BusinessMetric, BeforeValidator(_coerce_to_business_metric)] = Field(
        default_factory=lambda: BusinessMetric(value=0.0, reference="原文未明确标明"),
        description="逾期日罚息比例（含条款出处）。value 为小数形式（如 0.5‰ → 0.0005）；reference 为精确条款号"
    )
    penalty_cap_rate: Annotated[BusinessMetric, BeforeValidator(_coerce_to_business_metric)] = Field(
        default_factory=lambda: BusinessMetric(value=0.0, reference="原文未明确标明"),
        description="累计违约金上限比例（含条款出处）。value 为小数形式（如 10% → 0.1）；reference 为精确条款号"
    )
    termination_penalty_rate: Annotated[BusinessMetric, BeforeValidator(_coerce_to_business_metric)] = Field(
        default_factory=lambda: BusinessMetric(value=0.0, reference="原文未明确标明"),
        description="解约或根本性违约赔偿比例（含条款出处）。value 为小数形式（如 15% → 0.15）；reference 为精确条款号"
    )
    service_period_days: Annotated[BusinessMetric, BeforeValidator(_coerce_to_business_metric)] = Field(
        default_factory=lambda: BusinessMetric(value=0.0, reference="原文未明确标明"),
        description="服务期限/合同有效期总天数（含条款出处）。将'自X起Y年'或'有效期至X'统一换算为总天数；reference 为精确条款号及起止日期原文"
    )
    items: List[ContractItem] = Field(
        default_factory=list, description="采购物品/服务明细清单，逐项提取每一项的品名、规格、数量、单价、位置"
    )


class DifferenceItem(BaseModel):
    """差异项，包含描述、原文摘录与法务起草的修改建议"""

    type: str = Field(
        default="",
        description="差异类型标签，如'价格偏差'、'【UPS电池组】小计计算错误'，用于前端卡片标题。",
    )
    description: str = Field(
        ...,
        description="详细说明差异的具体内容，必须明确指出'具体变了什么'。例如数字的变化（如：将付款周期从15天延长至30天）、金额的增减、或者主体的改变。绝对禁止只写'存在差异'、'不一致'等空泛概括。",
    )
    suggested_amendment: str = Field(
        default="",
        description="直接提供可供用户复制粘贴的修改后条款文本。不要只说'建议修改一致'，必须给出可直接写入合同的完整条款正文。",
    )
    original_text: str = Field(
        default="",
        description="必须一字不差地复制采购结果文件中的原句，严禁概括、同义替换或省略。用于展示采购结果侧原文。",
    )
    contract_text: str = Field(
        default="",
        description="必须一字不差地复制正式合同文件中的原句，严禁概括、同义替换或省略。用于展示合同侧原文。",
    )
    risk_comment: str = Field(
        default="",
        description="AI 针对本条差异生成的风险注释与审查意见，必须具象化（如'预付款比例由30%上调至50%，资金占用风险上升20个百分点'），禁止空泛概括。",
    )
    is_favorable_to_buyer: bool = Field(
        default=False,
        description="如果该差异对采购方/我方是绝对有利的（如质保期延长、违约金比例提高、付款条件更优），必须设为 true，且 suggested_amendment 必须为空字符串。",
    )


class MissingItem(BaseModel):
    """缺失项，包含描述、原文摘录与法务起草的补充条款"""

    clause_name: str = Field(
        default="",
        description="缺失条款的名称，如'增值服务'、'保密协议'、'知识产权归属'等，用于前端分类展示。",
    )
    description: str = Field(
        ...,
        description="详细说明缺失条款的具体内容。必须指出该条款在采购结果文件中的具体约定是什么，以及合同中缺失了什么。禁止空泛概括。",
    )
    suggested_amendment: str = Field(
        ...,
        description="直接提供可供用户复制粘贴的补充条款全文。必须是可直接写入合同的完整条款正文，不要只说'建议补充'。",
    )
    original_text: str = Field(
        default="",
        description="必须一字不差地复制采购结果文件中的原句（即合同中应该包含但缺失的条款原文），严禁概括。",
    )
    contract_text: str = Field(
        default="",
        description="必须一字不差地复制合同原文中本条款应出现位置的上下文原句，严禁概括。用于前端高亮锚点匹配。",
    )
    risk_comment: str = Field(
        default="",
        description="AI 针对本条缺失生成的风险注释与审查意见，必须具象化说明缺失带来的具体风险。",
    )


class CompareResult(BaseModel):
    """两份合同信息的最终比对结果（由三 Agent 接力产出）"""

    risk_level: str = Field(..., description="风险等级：high / medium / low")
    confidence_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="风控总管评定的全局置信度 0~1"
    )
    differences: List[DifferenceItem] = Field(default_factory=list, description="差异详情列表（含修改建议）")
    missing_items: List[MissingItem] = Field(default_factory=list, description="缺失条款列表（含补充建议）")
    matches: List[str] = Field(default_factory=list, description="一致项详情列表")
    agent_traces: List[dict] = Field(default_factory=list, description="多智能体协作轨迹记录")
    parsed_contract_text: str = Field(
        default="",
        description="解析后的最终合同纯文本，供前端左右双屏原文高亮使用",
    )


class PaymentNode(BaseModel):
    """财务付款节点"""

    node_name: str = Field(..., description="付款节点名称，如预付款、验收款、质保金等")
    percentage: float = Field(..., description="付款占比，如 0.3 表示 30%")
    amount: float = Field(..., description="付款金额（元），根据合同总金额与占比计算")
    condition: str = Field(..., description="付款条件，如合同签订后 7 日内、验收合格后等")


class FinancialInfo(BaseModel):
    """合同财务付款安排"""

    total_amount: Annotated[float, BeforeValidator(_coerce_unknown_to_zero)] = Field(
        0.0, description="合同总标的额（元），从文本中提取"
    )
    warranty_ratio: Annotated[float, BeforeValidator(_coerce_unknown_to_zero)] = Field(
        0.0, description="质保金留存比例，如 0.05 表示 5%"
    )
    payment_nodes: List[PaymentNode] = Field(default_factory=list, description="付款节点列表")
