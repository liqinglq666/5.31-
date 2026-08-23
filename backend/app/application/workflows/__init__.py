"""
app/application/workflows/__init__.py
-------------------------------------
应用层工作流聚合导出。
"""

from app.application.workflows.contract_review import (
    ContractReviewWorkflow,
    process_contract_review,
)

__all__ = ["ContractReviewWorkflow", "process_contract_review"]
