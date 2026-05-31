"""
agent_supervisor.py
-------------------
Agent C —— 首席风控官兼委员会主席（Chief Risk Officer & Chairman）。

MoE 架构中的最终裁决层。职责：
- 接收 Agent A（商务报告）、Agent B（法务报告）及物理引擎强制警报；
- 执行 CoVe（Chain-of-Verification）验证链：梳理合并 → 独立核实 → 疑罪从无；
- 对数学/物理警报绝对服从，一字不改；
- 输出统一格式的最终 JSON 裁决报告。

核心入口：
    report = await run_final_decision(agent_a_report, agent_b_report, physical_alerts, original_context, model_id)
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

from app.infrastructure.llm.client import chat_completion
from app.core.config import settings
from app.domain.agent.prompts import load_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 输出 Schema（与前端 CompareResult 对齐）
# ---------------------------------------------------------------------------

class FinalDifferenceItem(BaseModel):
    """裁决后的差异项（兼容前端 DifferenceItem）。"""

    type: str = Field(default="", description="面向用户展示的简短中文主标题，绝对禁止用英文！例如：'价格偏差'、'付款方式差异'、'条款缺失'")
    category_zh: str = Field(..., description="面向用户展示的精炼中文分类，例如：'价格偏差'、'质保期缩短'、'违约金变更'")
    clause_reference: str = Field(..., description="差异点在《正式合同》中的精确出处，例如：'第5条' 或 '附件二第3.1款'")
    description: str = Field(..., description="合并后的极简原子声明，明确指出具体变化")
    suggested_amendment: str = Field(
        default="",
        description="直接可写入合同的修改建议条款全文；若对采购方有利则留空",
    )
    original_text: str = Field(default="", description="采购结果侧原文摘录")
    contract_text: str = Field(default="", description="正式合同侧原文摘录")
    risk_comment: str = Field(
        default="",
        description="具象化风控注释，如'预付款比例由30%上调至50%，资金占用风险上升20个百分点'",
    )
    is_favorable_to_buyer: bool = Field(
        default=False,
        description="若该差异对采购方绝对有利（如质保期延长、违约金提高），设为 true",
    )


class FinalMissingItem(BaseModel):
    """裁决后的缺失项（兼容前端 MissingItem）。"""

    clause_name: str = Field(default="", description="缺失条款名称，如'保密协议'、'知识产权归属'")
    category_zh: str = Field(..., description="面向用户展示的精炼中文分类，例如：'条款缺失'、'附件缺失'")
    clause_reference: str = Field(..., description="缺失点在《正式合同》中本应出现的位置，例如：'第5条' 或 '附件二第3.1款'")
    description: str = Field(..., description="缺失描述，必须指出采购结果中的原文约定及合同缺失内容")
    suggested_amendment: str = Field(
        ...,
        description="可直接写入合同的补充条款全文",
    )
    original_text: str = Field(default="", description="采购结果中应包含但合同缺失的条款原文")
    contract_text: str = Field(default="", description="合同中本条款应出现位置的上下文原文")
    risk_comment: str = Field(default="", description="具象化风险注释")


class FinalDecisionReport(BaseModel):
    """风控总管最终裁决报告。"""

    risk_level: str = Field(..., description="风险等级：high / medium / low")
    confidence_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="全局置信度 0~1"
    )
    differences: List[FinalDifferenceItem] = Field(
        default_factory=list, description="合并去重后的差异列表"
    )
    missing_items: List[FinalMissingItem] = Field(
        default_factory=list, description="合并去重后的缺失列表"
    )
    matches: List[str] = Field(
        default_factory=list, description="经确认后认定一致的关键项"
    )
    review_comments: str = Field(
        default="",
        description="风控总管整体评审意见，必须包含对物理引擎警报的明确确认及合并差异总结",
    )


# ---------------------------------------------------------------------------
# System Prompt（已迁移至 domain/agent/prompts/supervisor.jinja2）
# ---------------------------------------------------------------------------

_SUPERVISOR_SYSTEM_PROMPT = load_prompt("supervisor")


# ---------------------------------------------------------------------------
# Prompt 构建
# ---------------------------------------------------------------------------

_MAX_CONTEXT_LEN = 12000


def _build_supervisor_prompt(
    agent_a_report: str,
    agent_b_report: str,
    physical_alerts: List[Dict[str, Any]],
    original_context: str,
) -> str:
    """将三源输入拼装为极度清晰的 User Prompt。"""
    physical_str = (
        json.dumps(physical_alerts, ensure_ascii=False, indent=2)
        if physical_alerts
        else "[]"
    )
    context_snippet = original_context[:_MAX_CONTEXT_LEN]
    if len(original_context) > _MAX_CONTEXT_LEN:
        context_snippet += "\n\n[原始上下文过长，已截断]"

    # Agent 报告截断：防止超长差异列表挤占 CoVe 输出空间
    _MAX_REPORT_LEN = 8000
    a_report = agent_a_report[:_MAX_REPORT_LEN]
    if len(agent_a_report) > _MAX_REPORT_LEN:
        a_report += "\n\n[Agent A 报告过长，已截断]"
    b_report = agent_b_report[:_MAX_REPORT_LEN]
    if len(agent_b_report) > _MAX_REPORT_LEN:
        b_report += "\n\n[Agent B 报告过长，已截断]"

    return f"""\
【原始合同上下文】
{context_snippet}

【商务专员报告 (Agent A)】
{a_report}

【法务专员报告 (Agent B)】
{b_report}

【物理引擎强制警报】
{physical_str}

【任务】
作为首席风控官，请严格遵循 System Prompt 中的 Chain-of-Verification 流程：
1. 先输出 <cove_verification> 自我质询；
2. 再输出最终 JSON 裁决报告（不要 markdown 代码块）。
"""


# ---------------------------------------------------------------------------
# 文本 ↔ JSON 分离解析
# ---------------------------------------------------------------------------

def _extract_cove_and_json(text: str) -> tuple[str, str]:
    """
    从 LLM 回复中分离 <cove_verification> 与 JSON 字符串。

    返回 (cove_text, json_text)。若任一缺失则返回空字符串。
    """
    text = text.strip()

    # 1. 提取 <cove_verification> ... </cove_verification>
    cove_pattern = re.compile(r"<cove_verification>(.*?)</cove_verification>", re.DOTALL)
    cove_match = cove_pattern.search(text)

    cove_text = ""
    post_cove = text
    if cove_match:
        cove_text = cove_match.group(1).strip()
        post_cove = text[cove_match.end() :]

    # 2. 提取 post_cove 中的 JSON（兼容 markdown 代码块）
    json_text = post_cove.strip()
    if json_text.startswith("```"):
        lines = json_text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        json_text = "\n".join(lines).strip()

    return cove_text, json_text


def _parse_final_report(json_text: str) -> Optional[FinalDecisionReport]:
    """尝试将 JSON 字符串解析为 FinalDecisionReport，失败返回 None。"""
    if not json_text:
        return None
    try:
        raw = json.loads(json_text)
    except json.JSONDecodeError as exc:
        logger.warning("[AgentC] JSON decode failed: %s. Raw: %s", exc, json_text[:500])
        return None

    if not isinstance(raw, dict):
        logger.warning("[AgentC] Expected dict, got %s", type(raw).__name__)
        return None

    # 容错：LLM 可能把 differences / missing_items 写成 null
    for key in ("differences", "missing_items", "matches"):
        if raw.get(key) is None:
            raw[key] = []

    try:
        return FinalDecisionReport.model_validate(raw)
    except Exception as exc:
        logger.warning("[AgentC] Pydantic validation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 兜底报告
# ---------------------------------------------------------------------------

def _fallback_report(error_msg: str) -> dict:
    """当 CoVe 流程完全失败时返回的兜底报告，确保下游不崩溃。"""
    return {
        "risk_level": "high",
        "confidence_score": 0.0,
        "differences": [],
        "missing_items": [],
        "matches": [],
        "review_comments": (
            f"【风控总管报告生成异常】{error_msg}。"
            "建议立即启动人工复核，重点检查物理引擎警报与原始合同文本。"
        ),
    }


# ---------------------------------------------------------------------------
# 核心：CoVe 决断 + 重试机制
# ---------------------------------------------------------------------------

async def run_final_decision(
    agent_a_report: str,
    agent_b_report: str,
    physical_alerts: List[Dict[str, Any]],
    original_context: str,
    model_id: Optional[str] = None,
) -> dict:
    """执行 Agent C 风控裁决，返回 dict 格式的最终报告。

    Args:
        agent_a_report: Agent A（商务审计）的 JSON 或文本报告。
        agent_b_report: Agent B（法务审计）的 JSON 或文本报告。
        physical_alerts: 物理引擎警报列表，如 tool_evidence 汇总。
        original_context: 原始合同文本上下文（用于核实）。
        model_id: 可选，指定底层 LLM 模型 ID。

    Returns:
        FinalDecisionReport 的字典表示。解析失败时返回兜底报告。
    """
    logger.info(
        "[AgentC] Starting final decision. a_len=%d b_len=%d alerts=%d",
        len(agent_a_report),
        len(agent_b_report),
        len(physical_alerts),
    )

    user_prompt = _build_supervisor_prompt(
        agent_a_report, agent_b_report, physical_alerts, original_context
    )

    messages: List[dict] = [
        {"role": "system", "content": _SUPERVISOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # -----------------------------------------------------------------
    # 第一次调用：完整 CoVe Prompt
    # -----------------------------------------------------------------
    try:
        raw_text, usage = await chat_completion(messages, model_id=model_id, temperature=-1.0, max_tokens=8192)
        logger.info("[AgentC] First call usage=%s", usage)
    except Exception as exc:
        logger.exception("[AgentC] LLM first call failed")
        return _fallback_report(f"LLM 首次调用失败: {exc}")

    cove_text, json_text = _extract_cove_and_json(raw_text)
    logger.info("[AgentC] CoVe length=%d, JSON length=%d", len(cove_text), len(json_text))

    report = _parse_final_report(json_text)
    if report is not None:
        result = report.model_dump()
        result["_cove_verification"] = cove_text  # 透传核实过程供审计
        result["_token_usage"] = usage  # 透传 token 消耗
        logger.info("[AgentC] Final decision succeeded. risks=%d miss=%d level=%s",
                    len(report.differences), len(report.missing_items), report.risk_level)
        return result

    # -----------------------------------------------------------------
    # 第二次调用（重试）：极简 Prompt，避免长 System Prompt 挤占上下文窗口
    # -----------------------------------------------------------------
    logger.warning("[AgentC] First parse failed, retrying with simplified prompt...")

    _RETRY_SYSTEM_PROMPT = """\
你是银行首席风控官。基于输入的三源报告，直接输出纯 JSON 裁决报告。
严禁输出 markdown 代码块、XML 标签或任何解释文字。

JSON Schema 要求：
{
  "risk_level": "high | medium | low",
  "confidence_score": 0.0~1.0,
  "differences": [
    {
      "type": "4~8字纯中文标题，禁止英文",
      "category_zh": "纯中文分类",
      "clause_reference": "《正式合同》中的精确出处，如'第5条'",
      "description": "差异描述",
      "suggested_amendment": "修改建议",
      "original_text": "采购结果原文摘录",
      "contract_text": "正式合同原文摘录",
      "risk_comment": "风控批注",
      "is_favorable_to_buyer": false
    }
  ],
  "missing_items": [
    {
      "clause_name": "缺失条款名",
      "category_zh": "纯中文分类",
      "clause_reference": "《正式合同》中本应出现的位置",
      "description": "缺失描述",
      "suggested_amendment": "补充条款全文",
      "original_text": "采购结果中的确凿原文摘录",
      "contract_text": "合同中应出现位置的上下文",
      "risk_comment": "风控注释"
    }
  ],
  "matches": [],
  "review_comments": "整体评审意见"
}

约束：
- differences 与 missing_items 为空时必须输出 []，禁止 null。
- 没有任何差异时 risk_level=low，confidence_score=1.0。
- 对物理引擎的数值警报绝对服从，一字不改。
- missing_items 只收录"采购结果中确有原文约定且合同被彻底删除"的条款；采购结果中本来就没有的条款禁止放入。
"""

    retry_messages = [
        {"role": "system", "content": _RETRY_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        retry_text, retry_usage = await chat_completion(
            retry_messages,
            model_id=model_id,
            temperature=-1.0,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )
        logger.info("[AgentC] Retry call usage=%s", retry_usage)
    except Exception as exc:
        logger.exception("[AgentC] LLM retry call failed")
        return _fallback_report(f"LLM 重试调用失败: {exc}")

    # 重试后直接当 JSON 解析
    retry_json = retry_text.strip()
    if retry_json.startswith("```"):
        lines = retry_json.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        retry_json = "\n".join(lines).strip()

    report = _parse_final_report(retry_json)
    if report is not None:
        result = report.model_dump()
        result["_cove_verification"] = ""
        result["_token_usage"] = retry_usage
        logger.info("[AgentC] Final decision succeeded after retry.")
        return result

    # -----------------------------------------------------------------
    # 完全兜底
    # -----------------------------------------------------------------
    logger.error("[AgentC] All parsing attempts failed. Raw first: %s... Raw retry: %s...",
                 raw_text[:300], retry_text[:300])
    return _fallback_report("两次 CoVe 解析均失败，无法提取有效 JSON")
