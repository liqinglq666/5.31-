"""
agent_business.py
-----------------
Agent A —— 首席商务审计员（Chief Business Auditor）。

MoE 架构中的第一位专家。职责极度聚焦：
- 只关注金额、数量、交期、违约金等硬商务指标；
- 对法务条款（管辖、知识产权、保密）完全无视；
- 绝对禁用心算，所有数值比对必须通过 Tool Calling 调用物理验证工具；
- 输出为原子化商务差异声明，附带原文出处。

核心入口：
    differences = await run_business_audit(bid_info, contract_info, model_id)
"""

import json
import logging
from collections import defaultdict
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.infrastructure.llm.client import chat_completion

from app.domain.agent.tools import compare_numerical_values, verify_math_formula

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 输出 schema
# ---------------------------------------------------------------------------

class BusinessDifference(BaseModel):
    """Agent A 输出的单条商务差异（原子声明）。"""

    field_name: str = Field(..., description="差异字段名，如 'delivery_days', 'unit_price', 'penalty_rate'")
    category: str = Field(..., description="差异类别：'mismatch' | 'missing_in_contract' | 'missing_in_bid' | 'calculation_error'")
    clause_reference: str = Field(default="原文未标明", description="提取出的精确条款号，例如'第5条/款'或'附件二'等。如果找不到则填'原文未标明'")
    description: str = Field(..., description="极简原子声明，例如 '交期由 45 天变更为 60 天'")
    bid_value: Optional[float] = Field(default=None, description="投标侧数值")
    contract_value: Optional[float] = Field(default=None, description="合同侧数值")
    is_favorable_to_buyer: Optional[bool] = Field(
        default=None,
        description="对采购方是否有利。True=有利，False=不利，None=无法判定",
    )
    original_text_bid: str = Field(default="", description="采购结果原文摘录")
    original_text_contract: str = Field(default="", description="正式合同原文摘录")
    tool_evidence: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="支撑本条差异的工具调用结果链（可审计）",
    )


# ---------------------------------------------------------------------------
# System Prompt（已迁移至 domain/agent/prompts/business.jinja2）
# ---------------------------------------------------------------------------
from app.domain.agent.prompts import load_prompt

_AGENT_A_SYSTEM_PROMPT = load_prompt("business")


# ---------------------------------------------------------------------------
# Tool Schema（OpenAI Function Calling 格式）
# ---------------------------------------------------------------------------

_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "compare_numerical_values",
            "description": (
                "Compare two numerical values extracted from the procurement bid and the signed contract. "
                "Use this tool whenever you need to determine if a business metric (price, quantity, delivery days, penalty rate, etc.) "
                "has changed between the bid and the contract. Never calculate or estimate differences in your head."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bid_val": {
                        "type": "number",
                        "description": "The numeric value from the procurement bid document. Must be a finite real number.",
                    },
                    "contract_val": {
                        "type": "number",
                        "description": "The numeric value from the signed contract document. Must be a finite real number.",
                    },
                    "field_name": {
                        "type": "string",
                        "description": (
                            "Human-readable identifier for the field being compared. "
                            "Examples: 'unit_price', 'delivery_days', 'penalty_rate_daily', 'total_amount'."
                        ),
                    },
                },
                "required": ["bid_val", "contract_val", "field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_math_formula",
            "description": (
                "Verify whether unit_price multiplied by quantity equals the stated total amount. "
                "Use this tool for every line item in the procurement list to catch arithmetic errors or hidden cost inflation. "
                "Never do multiplication in your head."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "unit_price": {
                        "type": "number",
                        "description": "Price per unit. Must be a non-negative finite number.",
                    },
                    "quantity": {
                        "type": "number",
                        "description": "Number of units. Must be a non-negative finite number.",
                    },
                    "actual_total": {
                        "type": "number",
                        "description": "The total amount explicitly stated in the document. Must be a non-negative finite number.",
                    },
                },
                "required": ["unit_price", "quantity", "actual_total"],
            },
        },
    },
]

_TOOL_MAP = {
    "compare_numerical_values": compare_numerical_values,
    "verify_math_formula": verify_math_formula,
}


# ---------------------------------------------------------------------------
# Python 先行：items 硬编码比对（确定性计算层）
# ---------------------------------------------------------------------------

def _compare_items_fields(bid_items, contract_items):
    """
    Python 硬编码比对 items，返回三类结果。
    暗坑防护：Duplicate Name Overwrite + Float Precision + 千分位逗号。
    """
    matched = []      # 程序已核对完全一致
    mismatches = []   # 程序已发现字段差异（直接生成 BusinessDifference）
    leftovers = []    # name 对不上，需要 LLM 判断是否是改名/缩写

    def _is_different(v1, v2, epsilon=0.01):
        """
        带容差的数值比对。Float Precision + 千分位逗号刺客防护：
        避免 199.999999 != 200.0 的误报，避免 '1000' != 1000 的类型陷阱，
        避免 100,000.00 因逗号导致 float() 抛错后进入字符串严格比对而误报。
        """
        try:
            # 清洗：转字符串 -> 剔除逗号和常见货币符号 -> 再转 float
            clean_v1 = str(v1).replace(",", "").replace("¥", "").replace("￥", "") if v1 is not None else "0"
            clean_v2 = str(v2).replace(",", "").replace("¥", "").replace("￥", "") if v2 is not None else "0"
            f1 = float(clean_v1)
            f2 = float(clean_v2)
        except (ValueError, TypeError):
            # 非数值型（如提取成了"见附件"），退化为严格相等
            return str(v1).strip() != str(v2).strip()
        return abs(f1 - f2) > epsilon

    # 1. 按 name 精确匹配 —— Duplicate Name Overwrite 防护
    # 合同侧同名 item 可能有多条（如分阶段报价），不用 dict 而用 defaultdict(list)
    contract_map = defaultdict(list)
    for item in contract_items:
        # 防御性编程：永远不要 100% 信任 LLM 吐出的 JSON 结构
        name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
        if name:
            contract_map[name].append(item)

    # 防御性编程：跳过无 name 的坏数据
    bid_names = {item.get("name") for item in bid_items if isinstance(item, dict) and item.get("name")}

    for bid_item in bid_items:
        if not isinstance(bid_item, dict):
            continue
        name = bid_item.get("name")
        if not name:
            continue  # 遇到坏数据直接跳过，防止 KeyError 导致整个工作流崩溃

        candidates = contract_map.get(name, [])

        if not candidates:
            # name 在合同侧找不到
            leftovers.append({"side": "bid", "item": bid_item})
            continue

        if len(candidates) > 1:
            # 暗坑：Duplicate Name Overwrite
            # 同名 item 在合同侧出现多次，程序无法判断对应关系，
            # 全部踢出给 LLM 做语义级合并/拆分判断
            leftovers.append({
                "side": "both",
                "reason": "duplicate_name_in_contract",
                "bid_item": bid_item,
                "contract_items": candidates,
            })
            continue

        c_item = candidates[0]
        # name 匹配成功，逐项字段比对（Float Precision 防护）
        fields = ["unit_price", "quantity", "total_price"]
        has_diff = False
        for f in fields:
            bid_val = bid_item.get(f) if isinstance(bid_item, dict) else getattr(bid_item, f, None)
            c_val = c_item.get(f) if isinstance(c_item, dict) else getattr(c_item, f, None)
            if _is_different(bid_val, c_val):
                mismatches.append({
                    "name": name,
                    "field": f,
                    "bid_value": bid_val,
                    "contract_value": c_val,
                    "bid_position": bid_item.get("position", "") if isinstance(bid_item, dict) else "",
                    "contract_position": c_item.get("position", "") if isinstance(c_item, dict) else "",
                })
                has_diff = True
        if not has_diff:
            matched.append(name)

    # 2. 检查合同侧独有的 item（且未被 leftovers 覆盖的）
    for c_item in contract_items:
        if not isinstance(c_item, dict):
            continue
        c_name = c_item.get("name")
        if c_name and c_name not in bid_names:
            leftovers.append({"side": "contract", "item": c_item})

    return matched, mismatches, leftovers


# ---------------------------------------------------------------------------
# Python 先行：标量字段硬编码比对（确定性计算层）
# ---------------------------------------------------------------------------

_SCALAR_FIELDS = [
    "total_amount",
    "delivery_days",
    "service_period_days",
    "delay_daily_rate",
    "penalty_rate_daily",
    "penalty_cap_rate",
    "termination_penalty_rate",
    "warranty_period_days",
    "advance_payment_rate",
    "final_payment_rate",
]


def _extract_scalar(field_val):
    """从可能为嵌套对象 {{value, reference}} 或直接数值的字段中提取数值和出处。"""
    if field_val is None:
        return None, ""
    if isinstance(field_val, dict):
        val = field_val.get("value")
        ref = field_val.get("reference", "")
        if val is None:
            return None, ref
        try:
            return float(val), ref
        except (ValueError, TypeError):
            return None, ref
    try:
        return float(field_val), ""
    except (ValueError, TypeError):
        return None, ""


def _compare_scalar_fields(bid_info: dict, contract_info: dict) -> tuple[list[str], list[dict]]:
    """比对两侧标量字段，返回 (matched_fields, diff_dicts)。"""
    matched: list[str] = []
    diffs: list[dict] = []

    for field in _SCALAR_FIELDS:
        bid_val, bid_ref = _extract_scalar(bid_info.get(field))
        c_val, c_ref = _extract_scalar(contract_info.get(field))

        if bid_val is None and c_val is None:
            continue

        clause_ref = bid_ref or c_ref or "原文未标明"

        if bid_val is None:
            diffs.append({
                "field_name": field,
                "category": "missing_in_bid",
                "clause_reference": clause_ref,
                "description": f"合同中的【{field}】在采购结果中缺失。",
                "bid_value": None,
                "contract_value": c_val,
                "is_favorable_to_buyer": None,
                "original_text_bid": "",
                "original_text_contract": str(c_val),
                "tool_evidence": [],
            })
        elif c_val is None:
            diffs.append({
                "field_name": field,
                "category": "missing_in_contract",
                "clause_reference": clause_ref,
                "description": f"采购结果中的【{field}】在合同中缺失。",
                "bid_value": bid_val,
                "contract_value": None,
                "is_favorable_to_buyer": None,
                "original_text_bid": str(bid_val),
                "original_text_contract": "",
                "tool_evidence": [],
            })
        elif abs(bid_val - c_val) > 0.01:
            diffs.append({
                "field_name": field,
                "category": "mismatch",
                "clause_reference": clause_ref,
                "description": f"【{field}】由 {bid_val} 变更为 {c_val}。",
                "bid_value": bid_val,
                "contract_value": c_val,
                "is_favorable_to_buyer": None,
                "original_text_bid": str(bid_val),
                "original_text_contract": str(c_val),
                "tool_evidence": [],
            })
        else:
            matched.append(field)

    return matched, diffs


def _build_item_diff(m: dict) -> dict:
    """将 Python 找出的数值差异，包装成标准的差异字典格式（与 LLM 输出 Schema 对齐）。"""
    return {
        "field_name": f"item_{m['name']}_{m['field']}",
        "category": "mismatch",
        "clause_reference": m.get("bid_position", "") or m.get("contract_position", "") or "原文未标明",
        "description": f"明细项【{m['name']}】的【{m['field']}】数值被篡改。",
        "bid_value": m.get("bid_value"),
        "contract_value": m.get("contract_value"),
        "is_favorable_to_buyer": None,
        "original_text_bid": str(m.get("bid_value", "")),
        "original_text_contract": str(m.get("contract_value", "")),
        "tool_evidence": [{"source": "python_hardcoded", "note": "系统自动核对发现数值差异"}],
    }


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

def _build_single_shot_prompt(
    bid_info: dict,
    contract_info: dict,
    matched: List[str],
    code_diffs: List[dict],
    leftovers: List[dict],
) -> str:
    """组装 Agent A V3.2 单发 Prompt（无 tool loop）。"""
    import json

    bid_json = json.dumps(contract_info_to_dict(bid_info), ensure_ascii=False, indent=2)
    contract_json = json.dumps(contract_info_to_dict(contract_info), ensure_ascii=False, indent=2)

    matched_list = "\n".join(f"- {n}" for n in matched) or "（无）"
    code_diffs_list = json.dumps(code_diffs, ensure_ascii=False, indent=2) if code_diffs else "（无）"
    leftovers_list = json.dumps(leftovers, ensure_ascii=False, indent=2) if leftovers else "（无）"

    return f"""\
【左侧：采购结果（Bid）结构化数据】
{bid_json}

【右侧：正式合同（Contract）结构化数据】
{contract_json}

【程序已精确核实的差异（你必须原样采纳，不要修改数值）】
以下差异已由 Python 程序逐项精确计算，你直接包含在最终输出中：
{code_diffs_list}

【程序已核实完全一致的明细】
以下 items 已核对 unit_price / quantity / total_price 完全一致，你不需要再检查：
{matched_list}

【需要你来判断的疑难明细】
以下 items 因 name 无法精确匹配而被程序标记为 leftovers，请你判断：
1. 它们是否是同一个 item 的改名、缩写或别称？
2. 如果是同一 item，金额是否有差异？
3. 如果不是同一 item，请按 missing_in_contract / missing_in_bid 输出。
{leftovers_list}

【任务】
基于以上全部信息，输出一个 JSON 数组。每个元素是一个差异对象，字段要求：
- field_name: 差异字段名
- category: 差异类别（mismatch | missing_in_contract | missing_in_bid | calculation_error）
- clause_reference: 条款出处
- description: 极简原子声明
- bid_value: 采购结果侧数值（如有）
- contract_value: 合同侧数值（如有）
- is_favorable_to_buyer: 对采购方是否有利（true / false / null）
- original_text_bid: 采购结果原文摘录
- original_text_contract: 正式合同原文摘录
- tool_evidence: 支撑证据（空数组即可）

约束：
1. 对于【程序已精确核实的差异】，请直接原样包含在输出数组中。
2. 对于【需要你来判断的疑难明细】，请基于语义判断后输出。
3. 严禁输出 markdown 代码块标记，直接输出纯 JSON。
4. 如果除了程序已核实的差异外没有其他新增差异，输出空数组 []。
5. 输出任何 original_text_bid / original_text_contract 时，严禁使用 "..." 或 "…" 省略原文。
"""


# ---------------------------------------------------------------------------
# Tool Executor（供统一执行器调用）
# ---------------------------------------------------------------------------

def _tool_executor(func_name: str, args: dict) -> Any:
    """执行 Agent A 的本地工具。"""
    tool_fn = _TOOL_MAP.get(func_name)
    if tool_fn is None:
        return {"error": f"Unknown tool '{func_name}'. Available: {list(_TOOL_MAP.keys())}"}
    try:
        return tool_fn(**args)
    except Exception as exc:
        return {"error": f"Tool execution failed: {exc}"}


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------

async def run_business_audit(
    bid_info: dict,
    contract_info: dict,
    model_id: Optional[str] = None,
) -> tuple[List[dict], dict]:
    """执行 Agent A 商务审计（V3.2 单发版），返回 (差异字典列表, token_usage)。

    V3.2 架构：
    - Python 层完成 items + 标量字段的确定性比对（零 LLM 调用）。
    - 仅剩 leftovers（name 对不上的疑难明细）交给 LLM 单次调用判断。
    - 彻底弃用 25 轮 tool loop，速度从 2~3 分钟降至 5~10 秒。
    """
    logger.info("[AgentA] Starting SINGLE-SHOT business audit. bid_vendor=%s contract_vendor=%s",
                bid_info.get("vendor_name", "?"), contract_info.get("vendor_name", "?"))

    # ------------------------------------------------------------------
    # 1. Python 先行：items 确定性比对
    # ------------------------------------------------------------------
    bid_items = bid_info.get("items") or []
    contract_items = contract_info.get("items") or []
    matched, mismatches, leftovers = _compare_items_fields(bid_items, contract_items)

    # ------------------------------------------------------------------
    # 2. Python 先行：标量字段确定性比对
    # ------------------------------------------------------------------
    _scalar_matched, scalar_diffs = _compare_scalar_fields(bid_info, contract_info)

    # 3. 合并代码级差异
    item_diffs = [_build_item_diff(m) for m in mismatches]
    code_diffs = item_diffs + scalar_diffs
    logger.info(
        "[AgentA] Python 先行比对完成: items_matched=%d items_mismatches=%d items_leftovers=%d scalar_diffs=%d",
        len(matched), len(mismatches), len(leftovers), len(scalar_diffs),
    )

    # ------------------------------------------------------------------
    # 4. 单发 LLM：仅处理 leftovers（如无 leftovers 且 code_diffs 已完整，可跳过）
    # ------------------------------------------------------------------
    llm_diffs_dicts: List[dict] = []
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if leftovers or not code_diffs:
        # 有疑难明细需要 LLM 判断，或者完全没有差异需要 LLM 确认
        messages: List[dict] = [
            {"role": "system", "content": _AGENT_A_SYSTEM_PROMPT},
            {"role": "user", "content": _build_single_shot_prompt(
                bid_info, contract_info,
                matched=matched, code_diffs=code_diffs, leftovers=leftovers,
            )},
        ]

        try:
            final_text, usage = await chat_completion(
                messages, model_id=model_id, max_tokens=4096,
            )
        except Exception as exc:
            logger.exception("[AgentA] Single-shot LLM call failed")
            # LLM 调用失败时，至少返回 Python 已确认的 code_diffs
            return code_diffs, usage

        # 5. 解析 LLM 最终 JSON 输出
        llm_diffs = _parse_differences(final_text) or []
        llm_diffs_dicts = [
            d.model_dump() if hasattr(d, "model_dump") else d for d in llm_diffs
        ]

    # 6. 合并：Python 差异 + LLM 差异（LLM 应该包含 code_diffs，但为防遗漏做并集）
    #    用 field_name + category + description 去重
    seen_keys: set[str] = set()
    all_diffs: List[dict] = []
    for d in code_diffs + llm_diffs_dicts:
        key = f"{d.get('field_name')}:{d.get('category')}:{d.get('description', '')[:40]}"
        if key not in seen_keys:
            seen_keys.add(key)
            all_diffs.append(d)

    logger.info(
        "[AgentA] Audit complete. code_diffs=%d llm_diffs=%d total=%d usage=%s",
        len(code_diffs), len(llm_diffs_dicts), len(all_diffs), usage,
    )
    return all_diffs, usage


def _parse_differences(text: str) -> List[BusinessDifference]:
    """从 LLM 最终回复中解析 JSON 数组，容错处理 markdown 代码块。"""
    text = text.strip()

    # 去除可能的 markdown 代码块包裹
    if text.startswith("```"):
        lines = text.splitlines()
        # 去掉首行 ```json 或 ```
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 去掉末行 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if not text:
        return []

    try:
        raw_list = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("[AgentA] Failed to parse final response as JSON: %s. Raw text: %s", exc, text[:500])
        return []

    if not isinstance(raw_list, list):
        logger.warning("[AgentA] Expected JSON array, got %s. Wrapping in list.", type(raw_list).__name__)
        raw_list = [raw_list] if isinstance(raw_list, dict) else []

    results: List[BusinessDifference] = []
    for idx, item in enumerate(raw_list):
        if not isinstance(item, dict):
            continue
        # 容错：LLM 常把单条 tool_evidence 写成 dict 而非 list
        te = item.get("tool_evidence")
        if te is not None and not isinstance(te, list):
            item["tool_evidence"] = [te] if te else []
        try:
            diff = BusinessDifference.model_validate(item)
            results.append(diff)
        except Exception as exc:
            logger.warning("[AgentA] Difference item %d validation failed: %s", idx, exc)
            continue

    return results


# ---------------------------------------------------------------------------
# 便捷：将 ContractInfo / FinancialInfo 转为 dict（保留字段名映射）
# ---------------------------------------------------------------------------

def contract_info_to_dict(info: Any) -> dict:
    """将 Pydantic 模型实例安全地转为纯 Python dict，供 Agent 审计使用。

    使用 model_dump_json() -> json.loads() 的强制往返，确保嵌套 BaseModel
    （如 BusinessMetric）被彻底序列化为原生 dict，杜绝 'not JSON serializable'。
    """
    if isinstance(info, dict):
        return info
    if hasattr(info, "model_dump_json"):
        # Pydantic v2: 先转 JSON 字符串再转回 dict，深度序列化最保险
        return json.loads(info.model_dump_json())
    if hasattr(info, "json"):
        # Pydantic v1 fallback
        return json.loads(info.json())
    if hasattr(info, "dict"):
        return info.dict()  # type: ignore[call-arg]
    return dict(info)
