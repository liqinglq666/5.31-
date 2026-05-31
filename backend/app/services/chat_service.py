"""
services/chat_service.py
------------------------
AI 助手聊天服务层：封装文档问答和通用聊天的 prompt 构建、消息组装与流式调用逻辑。
新增 model_id 透传能力，支持 Copilot 动态切换底层模型。
"""

import asyncio
import json
from typing import List, Dict, Any, AsyncIterable, Optional

from app.models.models import TaskRecord
from app.infrastructure.llm.client import stream_chat_completion
from app.infrastructure.llm.dynamic_config import get_cached_active_model
from app.schemas.chat import ChatMessageRequest, GeneralChatRequest
from app.services.web_search import search_web, format_search_results


SYSTEM_PROMPT_TEMPLATE = """你是一位专业的银行法务审计助手，擅长解读采购结果与正式合同的比对报告。
请基于以下任务上下文，准确、严谨地回答用户的提问。
如果问题超出上下文范围，请明确告知用户。

【任务上下文】
{context}
"""

GENERAL_SYSTEM_PROMPT_TEMPLATE = """你是一位专业的银行法务审计助手，擅长合同审查、风险识别和合规建议。

{context}

请根据以上上下文和用户的问题，提供专业、准确、实用的回答。
如果用户询问最近检测的文件，请使用上下文中的最近文件信息回答。
如果问题涉及具体合同数据但上下文未提供，请引导用户前往具体合同页面进行咨询。
如果提供了联网搜索结果，请在回答中参考并注明来源。"""


def build_document_context(record: TaskRecord) -> str:
    """从 TaskRecord 中提取可用上下文文本，用于文档问答。"""
    parts = []
    if record.file_a_name:
        parts.append(f"采购结果文件：{record.file_a_name}")
    if record.file_b_name:
        parts.append(f"正式合同文件：{record.file_b_name}")
    if record.result:
        result = record.result
        comparison = result.get("comparison", {})
        bid_info = result.get("bid_info", {})
        contract_info = result.get("contract_info", {})
        parts.append("\n【AI 比对结果】")
        parts.append(f"风险等级：{comparison.get('risk_level', '未知')}")
        parts.append(f"比对结论：{comparison.get('conclusion', '暂无结论')}")
        differences = comparison.get("differences", [])
        missing_items = comparison.get("missing_items", [])
        all_issues = differences + missing_items
        if all_issues:
            parts.append("差异详情：")
            for idx, item in enumerate(all_issues, 1):
                if isinstance(item, dict):
                    desc = item.get("description", "")
                    parts.append(f"  {idx}. {desc}")
                else:
                    parts.append(f"  {idx}. {item}")
        def _fmt_penalty_matrix(info):
            delay = info.get('delay_daily_rate', 0)
            cap = info.get('penalty_cap_rate', 0)
            term = info.get('termination_penalty_rate', 0)
            parts = []
            if delay:
                parts.append(f"日罚息{delay * 100:g}%")
            if cap:
                parts.append(f"累计上限{cap * 100:g}%")
            if term:
                parts.append(f"解约赔偿{term * 100:g}%")
            return "、".join(parts) if parts else "未明确约定"

        if bid_info:
            parts.append(
                f"\n采购结果关键信息："
                f"供应商 {bid_info.get('vendor_name', '未知')}, "
                f"金额 {bid_info.get('total_amount', '未知')} 元, "
                f"交期 {bid_info.get('delivery_days', '未知')} 天, "
                f"违约金矩阵({_fmt_penalty_matrix(bid_info)})"
            )
        if contract_info:
            parts.append(
                f"正式合同关键信息："
                f"供应商 {contract_info.get('vendor_name', '未知')}, "
                f"金额 {contract_info.get('total_amount', '未知')} 元, "
                f"交期 {contract_info.get('delivery_days', '未知')} 天, "
                f"违约金矩阵({_fmt_penalty_matrix(contract_info)})"
            )
    return "\n".join(parts)


def build_document_messages(request: ChatMessageRequest, context: str) -> List[dict]:
    """组装文档问答的 OpenAI 原生消息列表。"""
    messages: List[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(context=context)}
    ]
    for msg in request.history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": request.message})
    return messages


def build_general_messages(request: GeneralChatRequest, context: str = "") -> List[dict]:
    """组装通用聊天的 OpenAI 原生消息列表。"""
    system_prompt = (
        GENERAL_SYSTEM_PROMPT_TEMPLATE.format(context=context)
        if context
        else GENERAL_SYSTEM_PROMPT_TEMPLATE.format(context="暂无额外上下文信息。")
    )
    messages: List[dict] = [{"role": "system", "content": system_prompt}]
    for msg in request.history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": request.message})
    return messages


async def stream_chat_response(
    messages: List[dict], model_id: Optional[str] = None
) -> AsyncIterable[str]:
    """异步生成器：调用 LLM 流式接口并逐块 yield。
    在首条 system prompt 中注入当前激活模型身份，使 Copilot 能回答模型相关问题。
    """
    active = get_cached_active_model()
    model_name = active["model_name"] if active else "未知模型"

    # 复制消息列表，避免原地修改传入的引用
    enriched_messages = list(messages)
    if enriched_messages and enriched_messages[0].get("role") == "system":
        original = enriched_messages[0]["content"]
        enriched_messages[0] = {
            "role": "system",
            "content": (
                f"{original}\n\n【系统提示】你当前由 {model_name} 大模型提供底层能力支持。"
                "当用户直接询问你的模型身份、版本或底层技术时，请如实回答。"
            ),
        }

    async for text in stream_chat_completion(enriched_messages, model_id):
        yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)  # 让出事件循环，减少 ASGI 缓冲


class ChatService:
    """聊天服务类，封装上下文构建与消息组装逻辑。"""

    def __init__(self, db):
        self.db = db

    # -----------------------------------------------------------------------
    # 文档问答
    # -----------------------------------------------------------------------
    @staticmethod
    def build_document_chat_messages(request: ChatMessageRequest, record: TaskRecord) -> List[dict]:
        context = build_document_context(record)
        return build_document_messages(request, context)

    # -----------------------------------------------------------------------
    # 通用聊天
    # -----------------------------------------------------------------------
    async def build_general_context(self, page_id: str) -> str:
        """根据页面 ID 构建通用聊天的上下文文本。"""
        if page_id == "dashboard":
            from app.services.dashboard_service import CopilotService
            from app.crud.crud_task import count_tasks

            copilot_service = CopilotService(self.db)
            recent_task = await copilot_service._get_recent_task()
            total_count = await count_tasks(self.db)

            context_parts = [f"系统累计检测合同总数：{total_count} 份。"]

            if recent_task:
                context_parts.append("\n【最近检测的文件信息】")
                context_parts.append(f"- 项目名称：{recent_task.get('project_name', '未知')}")
                context_parts.append(f"- 供应商：{recent_task.get('vendor_name', '未知')}")
                context_parts.append(f"- 合同金额：{recent_task.get('amount', '未知')}")
                context_parts.append(f"- 风险等级：{recent_task.get('risk_level', '未知')}")
                context_parts.append(f"- 检测时间：{recent_task.get('created_at', '未知')}")
                context_parts.append(f"- 结论摘要：{recent_task.get('conclusion', '暂无')}")

            return "\n".join(context_parts)

        return ""

    def build_general_chat_messages(self, request: GeneralChatRequest, context: str = "") -> List[dict]:
        return build_general_messages(request, context)

    # -----------------------------------------------------------------------
    # 联网搜索 + 流式响应
    # -----------------------------------------------------------------------
    async def stream_response(
        self,
        messages: List[dict],
        model_id: Optional[str] = None,
        search: bool = False,
        user_message: str = "",
    ) -> AsyncIterable[str]:
        """流式响应，注入当前模型身份到 system prompt，支持联网搜索。"""
        active = get_cached_active_model()
        model_name = active["model_name"] if active else "未知模型"

        enriched_messages = list(messages)

        # 如果开启联网搜索，先搜索并把结果注入 system prompt
        if search and user_message:
            search_results = search_web(user_message, max_results=5)
            search_text = format_search_results(search_results)
            if search_text and enriched_messages and enriched_messages[0].get("role") == "system":
                enriched_messages[0]["content"] += f"\n\n{search_text}"

        if enriched_messages and enriched_messages[0].get("role") == "system":
            original = enriched_messages[0]["content"]
            enriched_messages[0] = {
                "role": "system",
                "content": (
                    f"{original}\n\n【系统提示】你当前由 {model_name} 大模型提供底层能力支持。"
                    "当用户直接询问你的模型身份、版本或底层技术时，请如实回答。"
                ),
            }

        async for text in stream_chat_completion(enriched_messages, model_id):
            yield text
