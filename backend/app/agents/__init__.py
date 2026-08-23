"""
兼容层：app.agents → domain.agent
旧导入路径保持可用，新代码请使用 app.domain.agent
"""

from app.domain.agent.tools import compare_numerical_values, verify_math_formula
from app.domain.agent.experts.business import run_business_audit, contract_info_to_dict
from app.domain.agent.experts.legal import run_legal_audit
from app.domain.agent.experts.supervisor import run_final_decision

__all__ = [
    "compare_numerical_values",
    "verify_math_formula",
    "run_business_audit",
    "contract_info_to_dict",
    "run_legal_audit",
    "run_final_decision",
]
