"""
services/rectification_service.py
---------------------------------
整改函生成服务层：封装 prompt 构建与 LLM 流式调用逻辑。
新增 model_id 透传能力，支持动态切换底层模型。
"""

from typing import List, AsyncIterable, Optional

from app.models.models import TaskRecord
from app.infrastructure.llm.client import stream_chat_completion


RECTIFICATION_SYSTEM_PROMPT = """你是一位资深的银行法务合规官，擅长撰写正式、严谨的法律文书。
请根据以下合同比对中发现的风险点，撰写一份《合同合规整改告知函》。

要求：
1. 格式正式，措辞严谨，符合银行内部合规文书规范。
2. 包含致辞（致供应商/合作方的抬头）。
3. 列出问题清单：每条风险点需单独成段，并附带具体的改进建议。
4. 结尾需包含整改期限要求、联系人信息占位符以及落款格式。
5. 语气保持专业且不失礼貌，但须明确表达整改的严肃性。

【比对任务信息】
- 采购结果文件：{file_a_name}
- 正式合同文件：{file_b_name}

【发现的风险点】
{risk_points}
"""


def build_rectification_messages(record: TaskRecord) -> List:
    """构建整改函生成的 LLM 消息列表。"""
    result = record.result or {}
    comparison = result.get("comparison", {})
    differences = comparison.get("differences", [])
    missing_items = comparison.get("missing_items", [])
    all_issues = differences + missing_items

    # 如果违约金矩阵在结构化信息层面不一致，前置到风险点列表
    bid_info = result.get("bid_info", {})
    contract_info = result.get("contract_info", {})

    def _check_penalty_field(field_name, label):
        b_val = bid_info.get(field_name, 0) or 0
        c_val = contract_info.get(field_name, 0) or 0
        if b_val and c_val and abs(float(b_val) - float(c_val)) > 1e-6:
            b_pct = f"{float(b_val) * 100:.1f}%"
            c_pct = f"{float(c_val) * 100:.1f}%"
            return {
                "description": f"{label}严重偏离：采购结果约定为 {b_pct}，正式合同变更为 {c_pct}，卖方违约成本发生变化，需重点审核。",
                "suggested_amendment": f"请将合同{label}恢复至采购结果约定的 {b_pct}，确保违约条款不低于原始承诺。",
            }
        return None

    for field, label in [
        ("delay_daily_rate", "逾期日罚息比例"),
        ("penalty_cap_rate", "累计违约金上限比例"),
        ("termination_penalty_rate", "解约赔偿比例"),
    ]:
        issue = _check_penalty_field(field, label)
        if issue:
            all_issues.insert(0, issue)

    if not all_issues:
        all_issues = ["暂未发现明显风险点，建议保持关注。"]

    def _fmt_issue(item):
        if isinstance(item, dict):
            desc = item.get("description", "")
            sugg = item.get("suggested_amendment", "")
            if sugg:
                return f"{desc}（建议：{sugg}）"
            return desc
        return str(item)

    risk_points_text = "\n".join(
        [f"{idx}. {_fmt_issue(it)}" for idx, it in enumerate(all_issues, 1)]
    )

    system_content = RECTIFICATION_SYSTEM_PROMPT.format(
        file_a_name=record.file_a_name or "未知文件",
        file_b_name=record.file_b_name or "未知文件",
        risk_points=risk_points_text,
    )

    human_content = (
        "请基于以上风险点，生成一份完整的《合同合规整改告知函》，直接输出正文内容，"
        "不需要额外的解释或总结。"
    )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": human_content},
    ]


async def stream_rectification(
    messages: List[dict], model_id: Optional[str] = None
) -> AsyncIterable[str]:
    """异步生成器：调用 LLM 流式接口并逐块 yield。"""
    async for text in stream_chat_completion(messages, model_id):
        yield text


class RectificationService:
    """整改函生成服务类。"""

    @staticmethod
    def build_messages(record: TaskRecord) -> List[dict]:
        return build_rectification_messages(record)

    @staticmethod
    async def stream_response(
        messages: List[dict], model_id: Optional[str] = None
    ) -> AsyncIterable[str]:
        async for text in stream_chat_completion(messages, model_id):
            yield text
