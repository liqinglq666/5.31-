"""
agent_legal.py
--------------
Agent B —— 首席法务审计员（Chief Legal Auditor）。

V3.2 重构：彻底弃用 15 轮 tool loop，改为「并行预检索 + 单次 LLM 分析」。
速度从 3~5 分钟降至 30~60 秒，Token 消耗降低 60% 以上。

核心入口：
    risks = await run_legal_audit(bid_baseline, bid_doc_id, contract_doc_id, legal_topics, model_id)
"""

import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

from app.infrastructure.llm.client import chat_completion

# 复用的 TopoMemoryManager 单例（懒加载）
from app.infrastructure.vectorstore.milvus import TopoMemoryManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 输出 schema
# ---------------------------------------------------------------------------

class LegalDifference(BaseModel):
    """Agent B 输出的单条法务差异（原子声明）。"""

    topic: str = Field(..., description="审查主题，如 '违约责任', '知识产权', '争议解决'")
    category: str = Field(
        ...,
        description="差异类别：'wording_tampering'(措辞篡改) | 'missing_clause'(条款缺失) | 'reference_mismatch'(引用断裂) | 'risk_escalation'(风险升级)",
    )
    description: str = Field(
        ...,
        description="极简原子声明，例如 '合同将采购结果中的\"有权要求更换\"弱化为\"可以协商更换\"，削弱了我方救济权'",
    )
    bid_text: str = Field(default="", description="采购结果侧原文摘录")
    contract_text: str = Field(default="", description="正式合同侧原文摘录")
    risk_level: str = Field(..., description="风险等级：high / medium / low")
    suggested_amendment: str = Field(
        default="",
        description="直接可写入合同的修改建议条款全文",
    )
    evidence_from_graph: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="支撑本条结论的图谱检索证据链",
    )


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------
from app.domain.agent.prompts import load_prompt

_AGENT_B_SYSTEM_PROMPT = load_prompt("legal")


# ---------------------------------------------------------------------------
# TopoMemoryManager 单例
# ---------------------------------------------------------------------------
_topo_manager: Optional[TopoMemoryManager] = None


def _get_topo_manager() -> TopoMemoryManager:
    global _topo_manager
    if _topo_manager is None:
        _topo_manager = TopoMemoryManager()
    return _topo_manager


# ---------------------------------------------------------------------------
# 智能截断检索上下文
# ---------------------------------------------------------------------------

def _smart_truncate_context(full_context: str) -> str:
    """智能截断检索上下文：前 2 个 chunk 保留完整文本，3+ 仅保留标题+30 字摘要。"""
    if len(full_context) < 1200:
        return full_context

    chunks = re.split(r"\n--- 章节|\n▎底层原文：|\n▎宏观摘要：", full_context)
    if len(chunks) <= 2:
        return full_context

    preserved: List[str] = []
    for idx, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if not chunk:
            continue
        if idx < 2:
            preserved.append(chunk)
        else:
            lines = chunk.splitlines()
            title = lines[0] if lines else ""
            body = " ".join(lines[1:]) if len(lines) > 1 else ""
            summary = body[:30] + "..." if len(body) > 30 else body
            preserved.append(f"{title}\n  [摘要] {summary}")

    return "\n\n".join(preserved)


# ---------------------------------------------------------------------------
# 并行预检索：所有主题并发查合同条款
# ---------------------------------------------------------------------------

async def _pre_retrieve_all_topics(
    topo_manager: TopoMemoryManager,
    contract_doc_id: str,
    topics: List[str],
    top_k: int = 5,
) -> Dict[str, str]:
    """并发检索每个审查主题在合同中的相关条款，按主题返回截断后的文本。"""

    async def _retrieve(topic: str) -> tuple[str, str]:
        context = await topo_manager.retrieve_context(
            doc_id=contract_doc_id,
            query=topic,
            top_k=top_k,
        )
        return topic, _smart_truncate_context(context)

    results = await asyncio.gather(*[_retrieve(t) for t in topics])
    return {topic: ctx for topic, ctx in results}


# ---------------------------------------------------------------------------
# 单次分析 Prompt 构建
# ---------------------------------------------------------------------------

def _build_single_shot_prompt(
    bid_baseline: str,
    contract_doc_id: str,
    topic_retrievals: Dict[str, str],
) -> str:
    """组装单次 LLM 分析 Prompt（无 tool loop）。

    使用强烈的 Markdown 层级分隔，防止 LLM 在长文本中出现"Lost in the Middle"注意力衰减。
    """

    sections: List[str] = []
    for topic, ctx in topic_retrievals.items():
        if not ctx.strip():
            sections.append(f"## {topic}\n[未检索到相关条款]")
            continue

        # 把同一主题下的多个 chunk 拆分为带明确标签的片段
        chunks = re.split(r"\n\n+", ctx.strip())
        chunk_lines: List[str] = []
        for idx, chunk in enumerate(chunks, 1):
            if chunk.strip():
                chunk_lines.append(f"【检索片段 {idx}】\n{chunk.strip()}")

        sections.append(f"## {topic}\n" + "\n\n".join(chunk_lines))

    retrieval_section = "\n\n".join(sections)

    return f"""\
# 采购结果法务基线（唯一判决依据）
{bid_baseline}

---

# 合同检索内容（doc_id: {contract_doc_id}）
以下按审查主题分组，每个主题检索了最相关的 5 个语义 chunk，已做智能截断：

{retrieval_section}

---

# 审查任务
请作为首席法务审计员，手持上述"采购结果法务基线"，对"合同检索内容"进行法律权利边界与约束条款的比对审查。

## 审查要点（逐主题检查）
1. **权利动词弱化**：有权 → 可以、应当 → 可以、必须 → 应当 等。
2. **约束条件删除**：采购结果中明确规定的约束条件在合同中是否被删除或隐匿。
3. **交叉引用断裂**：合同提到"按第 X 条执行"，但第 X 条内容已变更、删除或不存在。
4. **条款缺失**：采购结果基线明确要求的事项，在合同检索内容中完全找不到对应条款。

## 判断原则
- 采购结果法务基线是你的**唯一判决依据**，禁止依赖训练数据或先验知识脑补。
- 如果某主题检索结果为空或明显不足，且基线对该主题有明确要求，**直接判定为"条款缺失"**。

# 输出格式
请直接输出一个 JSON 数组，每个元素是一个差异对象：
- topic: 审查主题名称
- category: 差异类别（wording_tampering / missing_clause / reference_mismatch / risk_escalation）
- description: 极简原子声明
- bid_text: 采购结果侧原文摘录
- contract_text: 合同侧原文摘录（如无则空字符串）
- risk_level: high / medium / low
- suggested_amendment: 修改建议条款全文
- evidence_from_graph: 支撑证据数组（无则空数组）

如果没有发现任何差异，输出空数组 []。

注意：不要输出 markdown 代码块标记，直接输出纯 JSON。
"""


# ---------------------------------------------------------------------------
# 公共入口：预检索 + 单次 LLM 分析
# ---------------------------------------------------------------------------

async def run_legal_audit(
    bid_baseline: str,
    bid_doc_id: str,
    contract_doc_id: str,
    legal_topics: Optional[List[str]] = None,
    model_id: Optional[str] = None,
) -> tuple[List[LegalDifference], dict]:
    """执行 Agent B 法务审计（V3.2 单发版），返回 (法务差异列表, token_usage)。

    流程：
    1. 并发预检索所有审查主题的合同条款（asyncio.gather，10 并发）。
    2. 将采购结果基线 + 检索结果拼成一份大上下文。
    3. 单次 chat_completion 直接输出 JSON 差异数组。
    4. 如解析失败，自动以 json_object response_format 重试一次。
    """
    topics = legal_topics or _default_legal_topics()
    logger.info(
        "[AgentB] Starting SINGLE-SHOT legal audit. bid_doc_id=%s contract_doc_id=%s topics=%d baseline_len=%d",
        bid_doc_id,
        contract_doc_id,
        len(topics),
        len(bid_baseline),
    )

    # 步骤 1：并行预检索所有主题
    topo_manager = _get_topo_manager()
    topic_retrievals = await _pre_retrieve_all_topics(
        topo_manager, contract_doc_id, topics, top_k=5
    )
    total_chars = sum(len(v) for v in topic_retrievals.values())
    logger.info("[AgentB] Pre-retrieval complete. total_chars=%d", total_chars)

    # 步骤 2：构建单次分析 Prompt
    prompt = _build_single_shot_prompt(bid_baseline, contract_doc_id, topic_retrievals)
    messages: List[dict] = [
        {"role": "system", "content": _AGENT_B_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    # 步骤 3：单次 LLM 调用（无 tool loop）
    final_text = ""
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    try:
        final_text, usage = await chat_completion(
            messages,
            model_id=model_id,
            max_tokens=8192,
        )
    except Exception as exc:
        logger.exception("[AgentB] Single-shot LLM call failed")
        return [], usage

    # 步骤 4：解析结果
    differences = _parse_legal_differences(final_text)

    # 兜底：解析失败且文本非空时，用 JSON mode 重试一次
    if not differences and final_text.strip():
        logger.warning("[AgentB] First parse got zero differences, retrying with JSON mode")
        try:
            retry_text, retry_usage = await chat_completion(
                messages,
                model_id=model_id,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )
            for k in usage:
                usage[k] = usage.get(k, 0) + retry_usage.get(k, 0)
            differences = _parse_legal_differences(retry_text)
            logger.info("[AgentB] JSON mode retry parsed %d differences", len(differences))
        except Exception as exc:
            logger.warning("[AgentB] JSON mode retry failed: %s", exc)

    logger.info(
        "[AgentB] Audit complete. risks_found=%d usage=%s",
        len(differences),
        usage,
    )
    return differences, usage


# ---------------------------------------------------------------------------
# 默认审查主题
# ---------------------------------------------------------------------------

def _default_legal_topics() -> List[str]:
    """默认高频法务审查主题。"""
    return [
        "违约责任与违约金",
        "知识产权归属",
        "保密义务",
        "不可抗力条款",
        "合同解除与终止条件",
        "争议解决方式",
        "免责条款",
        "权利与义务边界",
        "服务质量保证",
        "数据安全与隐私保护",
    ]


# ---------------------------------------------------------------------------
# JSON 解析与容错
# ---------------------------------------------------------------------------

def _extract_json_block(text: str) -> Optional[str]:
    """从混杂自然语言的文本中，用栈匹配提取最外层 JSON 数组或对象。"""
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        depth = 0
        start_idx = None
        for i, ch in enumerate(text):
            if ch == start_char:
                if depth == 0:
                    start_idx = i
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0 and start_idx is not None:
                    candidate = text[start_idx : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        pass
    return None


def _parse_legal_differences(text: str) -> List[LegalDifference]:
    """从 LLM 最终回复中解析 JSON 数组。支持自然语言包裹的容错提取。"""
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if not text:
        return []

    # 尝试1：直接解析
    try:
        raw_list = json.loads(text)
    except json.JSONDecodeError:
        # 尝试2：从自然语言中提取 JSON 块
        extracted = _extract_json_block(text)
        if extracted:
            try:
                raw_list = json.loads(extracted)
                logger.info("[AgentB] Extracted JSON block from natural language (%d chars)", len(extracted))
            except json.JSONDecodeError as exc:
                logger.warning("[AgentB] Failed to parse extracted JSON: %s. Raw text: %s", exc, text[:500])
                return []
        else:
            logger.warning("[AgentB] Failed to parse final response as JSON and no JSON block found. Raw text: %s", text[:500])
            return []

    if not isinstance(raw_list, list):
        logger.warning("[AgentB] Expected JSON array, got %s. Wrapping in list.", type(raw_list).__name__)
        raw_list = [raw_list] if isinstance(raw_list, dict) else []

    results: List[LegalDifference] = []
    for idx, item in enumerate(raw_list):
        if not isinstance(item, dict):
            continue
        efg = item.get("evidence_from_graph")
        if efg is not None and isinstance(efg, list):
            cleaned: List[Dict[str, Any]] = []
            for e in efg:
                if isinstance(e, dict):
                    cleaned.append(e)
                elif isinstance(e, str):
                    cleaned.append({"raw": e})
                else:
                    cleaned.append({"raw": str(e)})
            item["evidence_from_graph"] = cleaned
        try:
            diff = LegalDifference.model_validate(item)
            results.append(diff)
        except Exception as exc:
            logger.warning("[AgentB] Difference item %d validation failed: %s", idx, exc)
            continue

    return results
