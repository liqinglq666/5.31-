"""
domain/contract/
----------------
合同领域（Contract Domain）。

包含合同核心业务实体、值对象与结构化提取逻辑。
"""

from app.domain.contract.entities import (
    BusinessMetric,
    ContractItem,
    ContractInfo,
    DifferenceItem,
    MissingItem,
    CompareResult,
    PaymentNode,
    FinancialInfo,
    flatten_business_metrics,
)
from app.domain.contract.extractor import (
    extract_contract_info,
    extract_financial_info,
)

__all__ = [
    "BusinessMetric",
    "ContractItem",
    "ContractInfo",
    "DifferenceItem",
    "MissingItem",
    "CompareResult",
    "PaymentNode",
    "FinancialInfo",
    "flatten_business_metrics",
    "extract_contract_info",
    "extract_financial_info",
]
