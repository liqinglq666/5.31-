"""
app/agents/tools.py
-------------------
物理验证工具库（Tool Sandbox）。

将底层数值比对与数学验算逻辑封装为纯粹函数，
供 LLM 通过 Tool Calling 机制动态调用。

所有函数均具备：
1. 详尽的 Google Style Docstring（LLM 依赖其决定调用时机与参数填充）。
2. 强类型签名（PEP 484），便于静态分析与运行时校验。
3. 零外部依赖，仅使用 Python 标准库。
"""

from typing import Dict, Any


def compare_numerical_values(
    bid_val: float,
    contract_val: float,
    field_name: str,
) -> Dict[str, Any]:
    """Compare two numerical values from bid and contract, computing absolute diff and percentage change.

    This tool is designed for LLM-driven contract review workflows. When the LLM
    extracts corresponding numeric fields (e.g., unit price, penalty rate, delivery
    days) from both the procurement bid and the signed contract, it should invoke
    this function to obtain a canonical, machine-verified comparison result.

    Args:
        bid_val: The numeric value extracted from the procurement bid document.
            Must be a finite real number. Example: 1500.0
        contract_val: The numeric value extracted from the signed contract document.
            Must be a finite real number. Example: 1725.0
        field_name: Human-readable identifier for the field being compared.
            Used to contextualize the result in downstream LLM prompts.
            Example: "unit_price", "penalty_rate_daily", "delivery_days"

    Returns:
        A standardized dictionary with the following keys:

        - status (str): One of:
            - "match": Absolute difference <= 0.01 and percentage difference <= 0.1%.
            - "mismatch": Values differ beyond the tolerance threshold.
            - "missing_bid": ``bid_val`` is NaN or None-equivalent (not applicable here since type is float, but conceptually reserved).
            - "missing_contract``: ``contract_val`` is NaN or None-equivalent (reserved).
        - bid_value (float): Echo of ``bid_val``.
        - contract_value (float): Echo of ``contract_val``.
        - field_name (str): Echo of ``field_name``.
        - abs_diff (float): ``abs(bid_val - contract_val)``.
        - diff_pct (float | None): Percentage change relative to the bid value,
          calculated as ``(contract_val - bid_val) / bid_val * 100``.
          Returns ``None`` if ``bid_val`` is zero to avoid division by zero.
        - is_favorable (bool | None):
            - ``True`` if the change is favorable to the purchaser (e.g., lower price, shorter delivery, higher penalty for supplier).
            - ``False`` if unfavorable.
            - ``None`` if the favorability cannot be determined generically (e.g., for neutral metrics like "warranty_months" where directionality depends on clause context).
        - message (str): A concise human-readable summary suitable for direct
          inclusion in an LLM prompt or audit report.

    Raises:
        ValueError: If either ``bid_val`` or ``contract_val`` is not a finite number (inf or nan).

    Example:
        >>> compare_numerical_values(1500.0, 1725.0, "unit_price")
        {
            "status": "mismatch",
            "bid_value": 1500.0,
            "contract_value": 1725.0,
            "field_name": "unit_price",
            "abs_diff": 225.0,
            "diff_pct": 15.0,
            "is_favorable": False,
            "message": "unit_price: 合同值 1725.0 较投标值 1500.0 上涨 15.00%，对采购方不利。"
        }
    """
    import math

    for val, label in ((bid_val, "bid_val"), (contract_val, "contract_val")):
        if not isinstance(val, (int, float)):
            raise ValueError(f"{label} must be a number, got {type(val).__name__}")
        if math.isinf(val) or math.isnan(val):
            raise ValueError(f"{label} must be finite, got {val}")

    abs_diff = abs(bid_val - contract_val)
    tol_abs = 0.01
    tol_pct = 0.1

    if bid_val == 0:
        diff_pct = None
        # When bid is zero, any non-zero contract value is considered mismatch
        status = "match" if contract_val == 0 else "mismatch"
    else:
        diff_pct = (contract_val - bid_val) / bid_val * 100.0
        status = (
            "match"
            if abs_diff <= tol_abs and abs(diff_pct) <= tol_pct
            else "mismatch"
        )

    # Determine favorability heuristics based on field_name keywords
    favorable_higher = {
        "penalty_rate",
        "penalty_rate_daily",
        "deposit_ratio",
        "warranty_months",
        "quality_deposit_ratio",
        "liquidated_damages",
    }
    favorable_lower = {
        "unit_price",
        "total_price",
        "delivery_days",
        "lead_time",
        "payment_days",
    }

    fn_lower = field_name.lower()
    is_favorable: bool | None = None
    if any(k in fn_lower for k in favorable_higher):
        is_favorable = contract_val >= bid_val
    elif any(k in fn_lower for k in favorable_lower):
        is_favorable = contract_val <= bid_val

    if status == "match":
        message = f"{field_name}: 投标值 {bid_val} 与合同值 {contract_val} 一致。"
    else:
        pct_str = f"{diff_pct:+.2f}%" if diff_pct is not None else "N/A"
        direction = "对采购方有利" if is_favorable else "对采购方不利" if is_favorable is False else "需人工复核"
        message = (
            f"{field_name}: 合同值 {contract_val} 较投标值 {bid_val} 变动 {pct_str}，"
            f"绝对差值 {abs_diff:.2f}，{direction}。"
        )

    return {
        "status": status,
        "bid_value": bid_val,
        "contract_value": contract_val,
        "field_name": field_name,
        "abs_diff": abs_diff,
        "diff_pct": diff_pct,
        "is_favorable": is_favorable,
        "message": message,
    }


def verify_math_formula(
    unit_price: float,
    quantity: float,
    actual_total: float,
) -> Dict[str, Any]:
    """Verify whether ``unit_price * quantity`` equals ``actual_total`` within tolerance.

    This tool is intended for LLM-driven audit workflows where the model has
    extracted unit price, quantity, and total amount from tabular line items.
    If the computed total deviates from the stated total by more than 0.01,
    the function raises an alarm, helping catch arithmetic errors or hidden
    cost inflation in contract appendices.

    Args:
        unit_price: Price per unit. Must be a non-negative finite number.
            Example: 1200.50
        quantity: Number of units. Must be a non-negative finite number.
            Example: 3.0
        actual_total: The total amount explicitly stated in the document.
            Must be a non-negative finite number.
            Example: 3601.50

    Returns:
        A standardized dictionary with the following keys:

        - status (str): One of:
            - "correct``: Computed total matches ``actual_total`` within tolerance (<= 0.01).
            - "incorrect``: Deviation exceeds tolerance.
            - "warning``: One or more inputs are zero, producing a trivial result that may warrant manual review.
        - unit_price (float): Echo of ``unit_price``.
        - quantity (float): Echo of ``quantity``.
        - actual_total (float): Echo of ``actual_total``.
        - computed_total (float): ``unit_price * quantity``.
        - deviation (float): ``abs(computed_total - actual_total)``.
        - deviation_pct (float | None): Relative deviation percentage.
          ``deviation / actual_total * 100`` if ``actual_total > 0``, else ``None``.
        - message (str): Human-readable audit message suitable for inclusion
          in LLM prompts or risk tables.

    Raises:
        ValueError: If any argument is negative, infinite, or NaN.

    Example:
        >>> verify_math_formula(1200.50, 3.0, 3601.50)
        {
            "status": "correct",
            "unit_price": 1200.50,
            "quantity": 3.0,
            "actual_total": 3601.50,
            "computed_total": 3601.50,
            "deviation": 0.0,
            "deviation_pct": 0.0,
            "message": "小计验算通过: 单价 1200.50 * 数量 3.0 = 3601.50，与文档小计 3601.50 偏差 0.00 (0.00%)。"
        }

        >>> verify_math_formula(100.0, 2.0, 250.0)
        {
            "status": "incorrect",
            ...
            "message": "小计验算告警: 单价 100.0 * 数量 2.0 = 200.0，与文档小计 250.0 偏差 50.00 (20.00%)。存在隐性加价风险。"
        }
    """
    import math

    for val, label in (
        (unit_price, "unit_price"),
        (quantity, "quantity"),
        (actual_total, "actual_total"),
    ):
        if not isinstance(val, (int, float)):
            raise ValueError(f"{label} must be a number, got {type(val).__name__}")
        if math.isinf(val) or math.isnan(val):
            raise ValueError(f"{label} must be finite, got {val}")
        if val < 0:
            raise ValueError(f"{label} must be non-negative, got {val}")

    computed_total = unit_price * quantity
    deviation = abs(computed_total - actual_total)
    tolerance = 0.01

    if unit_price == 0 or quantity == 0:
        status = "warning"
    elif deviation <= tolerance:
        status = "correct"
    else:
        status = "incorrect"

    if actual_total > 0:
        deviation_pct = deviation / actual_total * 100.0
    else:
        deviation_pct = None

    pct_str = f"{deviation_pct:.2f}%" if deviation_pct is not None else "N/A"

    if status == "correct":
        message = (
            f"小计验算通过: 单价 {unit_price} * 数量 {quantity} = {computed_total}，"
            f"与文档小计 {actual_total} 偏差 {deviation:.2f} ({pct_str})。"
        )
    elif status == "warning":
        message = (
            f"小计验算提示: 单价 {unit_price} * 数量 {quantity} = {computed_total}，"
            f"与文档小计 {actual_total} 偏差 {deviation:.2f}。"
            f"因输入含零值，建议人工复核是否为赠送项或数据缺失。"
        )
    else:
        message = (
            f"小计验算告警: 单价 {unit_price} * 数量 {quantity} = {computed_total}，"
            f"与文档小计 {actual_total} 偏差 {deviation:.2f} ({pct_str})。"
            f"存在隐性加价或计算错误风险，建议重点核查。"
        )

    return {
        "status": status,
        "unit_price": unit_price,
        "quantity": quantity,
        "actual_total": actual_total,
        "computed_total": computed_total,
        "deviation": deviation,
        "deviation_pct": deviation_pct,
        "message": message,
    }
