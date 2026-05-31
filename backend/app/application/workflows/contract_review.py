"""
app/application/workflows/contract_review.py
-------------------------------------------
智契系统全局主控流水线（The Master Workflow）—— 重构版。

架构变更摘要：
- 旧版 document_parser.DoclingParserService 硬编码已移除，全面接入 Adapter Pattern。
- 引入依赖注入（DI），支持单元测试时注入 MockParser，无需拉起 Docling 视觉模型。
- 所有旧版正则嗅探、pdfplumber/PyMuPDF fallback、手工 Markdown 表格清洗逻辑已全部删除。
- 拓扑记忆层按 DDD 规划迁移至 app.infrastructure.vectorstore.milvus。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, List, Optional, Callable

# ------------------------------------------------------------------------------
# 【重构点 1】解析层防腐：彻底删除旧版 document_parser 硬编码，接入适配器接口
# ------------------------------------------------------------------------------
# ❌ 已删除：from app.services.document_parser import DoclingParserService
# ❌ 已删除：所有 pdfplumber / PyMuPDF / 正则嗅探 Markdown 表格的冗余导入与函数
from app.parsers import BaseDocumentParser, DoclingParserAdapter

# ------------------------------------------------------------------------------
# 【重构点 2】记忆层：已按 DDD 目录规划迁移至 app.infrastructure.vectorstore.milvus
# ------------------------------------------------------------------------------
from app.infrastructure.vectorstore.milvus import TopoMemoryManager

from app.domain.contract.extractor import extract_contract_info
from app.domain.contract.entities import flatten_business_metrics
from app.domain.agent.tools import verify_math_formula
from app.domain.agent.experts.business import run_business_audit, contract_info_to_dict
from app.domain.agent.experts.legal import run_legal_audit
from app.domain.agent.experts.supervisor import run_final_decision
from app.infrastructure.llm.client import chat_completion
from app.services.spatial_indexer import build_spatial_index
from app.domain.models.visual_evidence import SpatialIndex

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# 法务基线前置生成（Bid Baseline Generation）
# ------------------------------------------------------------------------------

_BID_BASELINE_PROMPT_TEMPLATE = (
    "你是一位严谨的法务摘要专家。请从以下《采购结果》文本中，"
    "针对给定的法务审查主题列表，一次性提取每个主题在采购结果中的核心约定。\n\n"
    "【采购结果原文】\n{bid_text}\n\n"
    "【审查主题列表】\n{topics_str}\n\n"
    "任务要求：\n"
    "1. 对每个主题，输出该主题在采购结果中的精确条款编号（如'第（七）条'、'附件一'）和核心原文摘录。\n"
    "2. 如果采购结果中确实没有提及某主题，明确标注'该主题在采购结果中未明确约定'。\n"
    "3. 不要添加任何你自己的解读或建议，只输出原文中确凿存在的客观事实。\n"
    "4. 输出格式为 Markdown 列表，每个主题一条。\n\n"
    "示例输出格式：\n"
    "- 违约责任与违约金：【采购结果第（七）条】逾期交付每日按合同总价1‰支付违约金，"
    "累计上限不超过合同总价10%；严重延误（逾期超过30个工作日）甲方有权解除合同。\n"
    "- 保密义务：该主题在采购结果中未明确约定（仅写'按合同约定执行'）。\n"
)


async def _generate_bid_legal_baseline(
    bid_md: str,
    legal_topics: List[str],
    model_id: Optional[str] = None,
) -> tuple[str, dict]:
    """生成采购结果法务基线。

    策略：
    - 若 bid_md < 8000 字符，直接返回原文（零幻觉、出处完整）。
    - 若 bid_md >= 8000 字符，调用单轮 LLM 生成结构化基线摘要。

    Returns:
        (baseline_text, token_usage)
    """
    if len(bid_md) < 8000:
        logger.info(
            "[BidBaseline] bid_md=%d chars < 8000, using full text injection.",
            len(bid_md),
        )
        return bid_md, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    topics_str = "\n".join(f"- {t}" for t in legal_topics)
    prompt = _BID_BASELINE_PROMPT_TEMPLATE.format(
        bid_text=bid_md[:12000],
        topics_str=topics_str,
    )
    messages = [
        {"role": "system", "content": "你是一位严谨的法务摘要专家，只输出客观事实。"},
        {"role": "user", "content": prompt},
    ]
    baseline, usage = await chat_completion(
        messages,
        model_id=model_id,
        temperature=-1.0,
    )
    logger.info(
        "[BidBaseline] Generated LLM summary. bid_md=%d chars baseline=%d chars tokens=%s",
        len(bid_md),
        len(baseline),
        usage,
    )
    return baseline, usage


# ------------------------------------------------------------------------------
# 空间索引归一化（供 _inject_visual_coordinates 复用）
# ------------------------------------------------------------------------------

import re as _spatial_re

_CJK_RADICAL_MAP = str.maketrans("⽇⽉⾄⽌⼄⽅⽬", "日月至止乙方目")


def _normalize_spatial(text: str) -> str:
    """归一化：剔除 Markdown 排版、换行、空格、全半角差异，用于空间索引匹配。"""
    if not text:
        return ""
    text = text.translate(_CJK_RADICAL_MAP)
    text = _spatial_re.sub(r"\s+", "", text)
    text = _spatial_re.sub(r"[，。；：！？\"'（）【】\[\]、\|\*]", "", text)
    return text.lower()


# ------------------------------------------------------------------------------
# Hallucination Guard —— Python 反幻觉预处理层（Stage 5 之前）
# ------------------------------------------------------------------------------

def _pre_validate_differences(
    diffs: List[Dict[str, Any]],
    bid_md: str,
    contract_md: str,
) -> List[Dict[str, Any]]:
    """在 Agent C 终审前，用 Python 对差异项做原文存在性验证。

    如果差异描述中的原文摘录在原始 Markdown 中找不到出处，标记为疑似幻觉。
    纯代码、零 token。
    """
    import re

    def _normalize(text: str) -> str:
        """归一化：剔除 Markdown 排版、换行、空格、全半角差异，用于模糊匹配。"""
        # 1. CJK 部首字符还原（OCR 误识别）
        text = text.translate(str.maketrans("⽇⽉⾄⽌⼄⽅⽬", "日月至止乙方目"))
        # 2. 全角数字/字母转半角（可选，视 OCR 质量决定）
        # 3. 剔除所有空白字符：空格、换行、制表符、连续空白
        text = re.sub(r"\s+", "", text)
        # 4. 剔除常见标点 + Markdown 格式符（Pipe Artifact 防护）
        #    注意：这里**不**剔除省略号，否则下游 _fuzzy_contains 的正则通配符会变成死代码
        #    必须剔除 Markdown 表格竖线 | 和加粗符 *，否则 Docling 原文保留竖线、
        #    LLM 提取删掉竖线，导致 str.find() 永远失败，真实风险被冤杀。
        text = re.sub(r"[，。；：！？\"'（）【】\[\]、\|\*]", "", text)
        return text.lower()

    def _fuzzy_contains(source: str, pattern: str) -> bool:
        """
        弹性包含检测。如果 pattern 中含有 "..."（省略号），
        将其视为通配符 .* 进行正则匹配，而不是直接 str.find()。
        这是 Ellipsis Assassin 暗坑的 Python 层补丁。
        """
        if "..." in pattern or "…" in pattern:
            # 分段处理：省略号变 .*?，其余字符安全转义
            parts = re.split(r'(\.{3}|…)', pattern)
            regex_pattern = ''.join(
                '.*?' if p in ('...', '…') else re.escape(p)
                for p in parts
            )
            return bool(re.search(regex_pattern, source))
        return pattern in source

    bid_norm = _normalize(bid_md)
    contract_norm = _normalize(contract_md)

    for diff in diffs:
        flags = []

        # 1. 检查 contract_text 是否存在于合同原文
        #    终极暗坑防护：LLM 可能显式输出 contract_text: null，
        #    diff.get(..., "") 对此无效（key 存在但值为 None），必须用 or "" 短路。
        contract_quote = diff.get("contract_text") or ""
        if contract_quote and len(contract_quote) > 10:
            q_norm = _normalize(contract_quote)
            if q_norm:
                # 先尝试精确包含，失败再用正则弹性匹配（Ellipsis Assassin 防护）
                if q_norm not in contract_norm and not _fuzzy_contains(contract_norm, q_norm):
                    flags.append("合同侧原文未找到确切出处")

        # 2. 检查 original_text 是否存在于采购结果原文
        #    同上防护：LLM 可能输出 original_text: null
        bid_quote = diff.get("original_text") or ""
        if bid_quote and len(bid_quote) > 10:
            q_norm = _normalize(bid_quote)
            if q_norm:
                if q_norm not in bid_norm and not _fuzzy_contains(bid_norm, q_norm):
                    flags.append("采购结果侧原文未找到确切出处")

        # 3. 如果任一侧找不到，降级风险并标注
        if flags:
            diff["risk_level"] = "low"
            diff["confidence_score"] = 0.3
            existing_rc = diff.get("risk_comment", "")
            halluc_note = "【系统反幻觉检测】" + "；".join(flags) + "，可能为 LLM 幻觉，建议人工复核。"
            diff["risk_comment"] = f"{existing_rc}\n{halluc_note}".strip()
            diff["__hallucination_flag"] = True

    return diffs


class ContractReviewWorkflow:
    """合同审查主控工作流（依赖注入版）。

    【重构点 3】通过构造函数注入解析器与记忆管理器，实现：
    1. 上层业务对底层引擎的完全无感知（面向 BaseDocumentParser 接口编程）。
    2. 单元测试时可注入 MockParser，避免在 CI 中拉起重型视觉模型。
    3. 未来替换为 Marker / MinerU 等新解析引擎时，无需修改本类任何代码。
    """

    def __init__(
        self,
        document_parser: Optional[BaseDocumentParser] = None,
        memory_manager: Optional[TopoMemoryManager] = None,
    ) -> None:
        # 若调用方未注入，默认使用 DoclingParserAdapter（生产环境行为不变）
        self.document_parser: BaseDocumentParser = (
            document_parser or DoclingParserAdapter()
        )
        self.memory_manager: TopoMemoryManager = (
            memory_manager or TopoMemoryManager()
        )

    # --------------------------------------------------------------------------
    # V3.1 视觉溯源：坐标注入钩子
    # --------------------------------------------------------------------------

    @staticmethod
    def _inject_visual_coordinates(
        diffs: List[Dict[str, Any]],
        spatial_index: Optional[SpatialIndex],
    ) -> List[Dict[str, Any]]:
        """在最终 JSON 返回前端前，将差异项与空间坐标索引匹配，注入 visual_evidence。"""
        if not spatial_index or not spatial_index.blocks:
            return diffs

        for diff in diffs:
            if not isinstance(diff, dict):
                continue
            quote = (
                diff.get("exact_quote")
                or diff.get("contract_text")
                or diff.get("original_text")
            )
            if not quote or len(quote) < 5:
                continue

            norm_quote = _normalize_spatial(quote)
            match = spatial_index.fuzzy_match(norm_quote)

            # 暗坑防护：Cross-Block Span —— 长句跨块匹配失败时，取头部锚点降级
            if not match and len(quote) > 15:
                match = spatial_index.fuzzy_match(norm_quote[:15])

            if match:
                diff["visual_evidence"] = {
                    "page_index": match.page_index,
                    "bbox": list(match.bbox),
                    "matched_text": match.norm_text,
                    "confidence": 1.0,
                }
        return diffs

    # --------------------------------------------------------------------------
    # 对外主入口
    # --------------------------------------------------------------------------

    async def process_contract_review(
        self,
        bid_pdf_path: str,
        contract_pdf_path: str,
        model_id: Optional[str] = None,
        price_tolerance: float = 0.0,
        required_clauses: Optional[List[str]] = None,
        custom_requirements: str = "",
        enable_visual_localization: bool = False,
        progress_callback: Optional[Callable[[int, str], Any]] = None,
    ) -> dict:
        """执行完整的五阶段合同审查流水线。

        Args:
            bid_pdf_path: 采购结果 PDF 的本地文件路径。
            contract_pdf_path: 正式合同 PDF 的本地文件路径。
            model_id: 可选，指定底层 LLM 模型 ID；默认使用 settings.llm_model。
            price_tolerance: 金额容差百分比，如 5.0 表示 ±5%。
            required_clauses: 必检条款名称清单。
            custom_requirements: 用户自定义的额外审查要求。

        Returns:
            包含五个阶段全部产出的 dict。
        """
        logger.info(
            "[MasterWorkflow] 开始全流程审查: bid=%s contract=%s",
            bid_pdf_path,
            contract_pdf_path,
        )

        async def _notify(progress: int, message: str) -> None:
            if progress_callback is not None:
                try:
                    result = progress_callback(progress, message)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass

        # ===================================================================
        # 阶段 1：物理摄入 —— 多模态解析（精简为两行接口调用）
        # ===================================================================
        logger.info("[Stage1] 物理摄入: 高保真 Markdown 解析中...")

        # 【重构点 4】旧版的多层 fallback 逻辑（pypdf 回退 / 正则嗅探 | 分隔符 /
        #   手工段落清洗 / 表格对齐修正）已彻底删除。现在统一走 BaseDocumentParser
        #   契约接口，由适配器内部通过 asyncio.to_thread 完成阻塞视觉解析的异步化。
        # 【稳定性修复】将并发解析改为串行，避免两个大 PDF 同时触发 RapidOCR/ONNX
        # 导致内存峰值冲垮容器（尤其在 WSL2 内存受限环境下）。
        bid_md = await self.document_parser.parse_to_markdown_async(bid_pdf_path)
        contract_md = await self.document_parser.parse_to_markdown_async(contract_pdf_path)
        logger.info(
            "[Stage1] 物理摄入完成: bid=%d chars, contract=%d chars",
            len(bid_md),
            len(contract_md),
        )
        await _notify(25, "PDF 解析完成，正在构建向量索引...")

        # ===================================================================
        # 【V3.1 旁路】空间坐标索引构建（视觉溯源）
        # ===================================================================
        spatial_task = None
        _spatial_task_id = uuid.uuid4().hex
        if enable_visual_localization:
            logger.info("[SpatialIndexer] 启动旁路空间索引协程...")
            spatial_task = asyncio.create_task(
                asyncio.to_thread(build_spatial_index, _spatial_task_id, contract_pdf_path)
            )

        # ===================================================================
        # 阶段 2：记忆构建 —— 拓扑记忆入库 + RAPTOR 摘要树
        # ===================================================================
        logger.info("[Stage2] 记忆构建: Milvus 入库与 RAPTOR 构建中...")

        bid_doc_id = f"bid_{uuid.uuid4().hex[:8]}"
        contract_doc_id = f"contract_{uuid.uuid4().hex[:8]}"

        bid_ingest, contract_ingest = await asyncio.gather(
            self.memory_manager.ingest_document(doc_id=bid_doc_id, md_text=bid_md),
            self.memory_manager.ingest_document(doc_id=contract_doc_id, md_text=contract_md),
        )
        logger.info(
            "[Stage2] 切片入库完成: bid_inserted=%d, contract_inserted=%d",
            bid_ingest.get("inserted", 0),
            contract_ingest.get("inserted", 0),
        )
        await _notify(35, "向量索引构建完成，正在提取合同结构化信息...")

        # 异步构建 RAPTOR 摘要树（真正非阻断——发射后不管）
        async def _bg_build_raptor(doc_id: str, model_id: Optional[str] = None) -> None:
            try:
                await self.memory_manager.build_raptor_tree(doc_id=doc_id, model_id=model_id)
                logger.info("[Stage2] RAPTOR 摘要树构建完成 doc_id=%s", doc_id)
            except Exception as exc:
                logger.warning("[Stage2] RAPTOR 构建失败（非阻断）: %s", exc)

        asyncio.create_task(_bg_build_raptor(bid_doc_id, model_id))
        asyncio.create_task(_bg_build_raptor(contract_doc_id, model_id))

        # ===================================================================
        # 阶段 3：提取与基础预检 —— 结构化提取 + Python 物理引擎批量验算
        # ===================================================================
        logger.info("[Stage3] 提取与预检: 结构化提取 + 物理引擎验算中...")

        # 3.1 结构化提取（注入用户自定义规则）
        rules: Optional[Dict[str, Any]] = None
        if price_tolerance or required_clauses or custom_requirements:
            rules = {
                "price_tolerance": price_tolerance,
                "required_clauses": required_clauses or [],
                "custom_requirements": custom_requirements,
            }

        # 并行提取（12K Head + 3K Tail 混合策略）
        bid_extract_task = extract_contract_info(
            bid_md,
            model_id=model_id,
            rules=rules,
            doc_id=bid_doc_id,
            memory_manager=self.memory_manager,
        )
        contract_extract_task = extract_contract_info(
            contract_md,
            model_id=model_id,
            rules=rules,
            doc_id=contract_doc_id,
            memory_manager=self.memory_manager,
        )
        (bid_info, bid_usage), (contract_info, contract_usage) = await asyncio.gather(
            bid_extract_task,
            contract_extract_task,
        )

        logger.info(
            "[Stage3] 提取完成: bid_vendor=%s, contract_vendor=%s rules=%s",
            bid_info.vendor_name,
            contract_info.vendor_name,
            rules,
        )

        # 3.2 物理引擎批量预跑：逐项验算单价 × 数量 == 小计
        physical_alerts: List[Dict[str, Any]] = []

        def _check_items(items, side_label: str):
            for item in items:
                if item.unit_price and item.quantity and item.total_price:
                    result = verify_math_formula(
                        unit_price=item.unit_price,
                        quantity=item.quantity,
                        actual_total=item.total_price,
                    )
                    if result["status"] == "incorrect":
                        physical_alerts.append(
                            {
                                "source": "物理引擎",
                                "tool": "verify_math_formula",
                                "side": side_label,
                                "item_name": item.name,
                                "type": "合同明细小计计算错误",
                                "description": result["message"],
                                "deviation": result.get("deviation"),
                                "deviation_pct": result.get("deviation_pct"),
                            }
                        )

        _check_items(bid_info.items, "采购结果")
        _check_items(contract_info.items, "正式合同")
        logger.info("[Stage3] 物理预检完成: alerts=%d", len(physical_alerts))
        await _notify(50, "结构化提取与物理预检完成，正在生成法务基线...")

        # ===================================================================
        # 阶段 4：异构委员会并发审查 —— Agent A（商务）+ Agent B（法务）
        # ===================================================================
        logger.info("[Stage4] 异构委员会: 并发启动 Agent A 与 Agent B...")

        # Agent A 输入：结构化 dict
        bid_dict = contract_info_to_dict(bid_info)
        contract_dict = contract_info_to_dict(contract_info)

        # Agent B 输入：法务主题列表 + 采购结果法务基线
        legal_topics = [
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

        # ===================================================================
        # 【新增】Stage 3.5：法务基线前置生成（Bid Baseline Generation）
        # ===================================================================
        logger.info("[Stage3.5] 法务基线前置生成中...")
        bid_baseline, baseline_usage = await _generate_bid_legal_baseline(
            bid_md=bid_md,
            legal_topics=legal_topics,
            model_id=model_id,
        )
        logger.info(
            "[Stage3.5] 基线生成完成. len=%d tokens=%s",
            len(bid_baseline),
            baseline_usage,
        )
        await _notify(60, "法务基线生成完成，正在执行商务与法务审计...")

        # 并发 gather，任一失败不阻塞另一方
        agent_a_coro = run_business_audit(
            bid_dict, contract_dict, model_id=model_id
        )
        agent_b_coro = run_legal_audit(
            bid_baseline=bid_baseline,
            bid_doc_id=bid_doc_id,
            contract_doc_id=contract_doc_id,
            legal_topics=legal_topics,
            model_id=model_id,
        )

        agent_a_raw, agent_b_raw = await asyncio.gather(
            agent_a_coro, agent_b_coro, return_exceptions=True
        )

        def _json_default(obj: Any) -> Any:
            """兜底 JSON 序列化器：遇到 Pydantic BaseModel 时自动转 dict。"""
            from pydantic import BaseModel

            if isinstance(obj, BaseModel):
                return obj.model_dump() if hasattr(obj, "model_dump") else obj.dict()
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

        # 序列化为 JSON 字符串供 Agent C 消费，同时提取 token 消耗
        agent_a_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if isinstance(agent_a_raw, Exception):
            logger.exception("[Stage4] Agent A 商务审计失败")
            agent_a_report = json.dumps(
                {"error": str(agent_a_raw)}, ensure_ascii=False, default=_json_default
            )
            agent_a_list: List[Any] = []
        else:
            agent_a_list, agent_a_usage = agent_a_raw
            # 兼容 run_business_audit 返回的 List[dict]（Python 代码差异）
            agent_a_report = json.dumps(
                [d if isinstance(d, dict) else d.model_dump() for d in agent_a_list],
                ensure_ascii=False, default=_json_default,
            )

        agent_b_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if isinstance(agent_b_raw, Exception):
            logger.exception("[Stage4] Agent B 法务审计失败")
            agent_b_report = json.dumps(
                {"error": str(agent_b_raw)}, ensure_ascii=False, default=_json_default
            )
            agent_b_list: List[Any] = []
        else:
            agent_b_list, agent_b_usage = agent_b_raw
            agent_b_report = json.dumps(
                [d if isinstance(d, dict) else d.model_dump() for d in agent_b_list],
                ensure_ascii=False, default=_json_default,
            )

        logger.info(
            "[Stage4] 并发审查结束: agent_a_diffs=%d agent_b_diffs=%d a_usage=%s b_usage=%s",
            len(agent_a_list),
            len(agent_b_list),
            agent_a_usage,
            agent_b_usage,
        )
        await _notify(75, "商务与法务审计完成，正在执行反幻觉检测...")

        # ===================================================================
        # 【新增】Stage 4.5：Python 反幻觉预处理（Hallucination Guard）
        # ===================================================================
        logger.info("[Stage4.5] Python 反幻觉预处理中...")
        if not isinstance(agent_a_raw, Exception):
            agent_a_dicts = [d if isinstance(d, dict) else d.model_dump() for d in agent_a_list]
            agent_a_list = _pre_validate_differences(agent_a_dicts, bid_md, contract_md)
            agent_a_report = json.dumps(agent_a_list, ensure_ascii=False, default=_json_default)
        if not isinstance(agent_b_raw, Exception):
            agent_b_dicts = [d if isinstance(d, dict) else d.model_dump() for d in agent_b_list]
            agent_b_list = _pre_validate_differences(agent_b_dicts, bid_md, contract_md)
            agent_b_report = json.dumps(agent_b_list, ensure_ascii=False, default=_json_default)
        logger.info("[Stage4.5] 反幻觉预处理完成")
        await _notify(85, "反幻觉检测完成，正在执行风控终审...")

        # ===================================================================
        # 阶段 5：风控终审 —— Agent C（CoVe 裁决）
        # ===================================================================
        logger.info("[Stage5] 风控终审: Agent C 执行 CoVe 决断中...")

        # 取前 4000 字符作为原始上下文供核实
        original_context = (
            f"【采购结果摘要】\n{bid_md[:4000]}\n\n"
            f"【正式合同摘要】\n{contract_md[:4000]}"
        )

        try:
            final_report = await run_final_decision(
                agent_a_report=agent_a_report,
                agent_b_report=agent_b_report,
                physical_alerts=physical_alerts,
                original_context=original_context,
                model_id=model_id,
            )
            logger.info(
                "[Stage5] 终审完成: risk_level=%s, confidence=%s",
                final_report.get("risk_level", "unknown"),
                final_report.get("confidence_score", "N/A"),
            )
            await _notify(95, "风控终审完成，正在组装最终结果...")
        except Exception as exc:
            logger.exception("[Stage5] Agent C 风控终审异常，降级为 Agent A/B 原始结果: %s", exc)
            # 降级策略：直接拼接 Agent A + Agent B + 物理引擎结果，避免任务整体崩溃
            combined_diffs = []
            if not isinstance(agent_a_raw, Exception):
                combined_diffs.extend([
                    d if isinstance(d, dict) else d.model_dump() for d in agent_a_list
                ])
            if not isinstance(agent_b_raw, Exception):
                combined_diffs.extend([
                    d if isinstance(d, dict) else d.model_dump() for d in agent_b_list
                ])

            final_report = {
                "risk_level": "high",
                "confidence_score": 0.0,
                "differences": combined_diffs,
                "missing_items": [],
                "matches": [],
                "review_comments": (
                    f"【风控终审降级】Agent C 因 API 额度耗尽或网络异常未能完成终审。"
                    f"以下为 Agent A（商务）与 Agent B（法务）的原始审查结果，请人工复核。"
                    f"异常详情: {str(exc)}"
                ),
                "_token_usage": {},
            }

        # ===================================================================
        # 阶段 6：记忆清理 —— 删除本次审查产生的 Milvus 临时数据，防止累积
        # ===================================================================
        try:
            await asyncio.gather(
                self.memory_manager.delete_by_doc_id(bid_doc_id),
                self.memory_manager.delete_by_doc_id(contract_doc_id),
            )
            logger.info(
                "[Stage6] Milvus 临时数据清理完成: bid=%s contract=%s",
                bid_doc_id,
                contract_doc_id,
            )
        except Exception as exc:
            logger.warning("[Stage6] Milvus 清理失败（非阻断）: %s", exc)

        # ===================================================================
        # 阶段 5.5：防御性后处理 —— 清除被 LLM 错误合并的物理引擎警报
        # ===================================================================
        # LLM 有时不严格遵守 prompt 约束，将物理引擎警报合并到违约金条款差异中。
        # 此处做兜底过滤：只有数值计算类差异才允许保留物理引擎警报标记。
        _PHYSICAL_ALERT_MARKER = "物理引擎强制警报"
        _NUMERIC_DIFF_TYPES = {
            "价格偏差", "数量差异", "合同明细小计计算错误", "总价计算错误",
            "amount_change", "price_deviation", "quantity_difference",
            "calculation_error", "total_price_error",
        }
        for diff in final_report.get("differences", []):
            diff_type = diff.get("type", "")
            rc = diff.get("risk_comment", "")
            if _PHYSICAL_ALERT_MARKER in rc and diff_type not in _NUMERIC_DIFF_TYPES:
                # 清除物理引擎警报标记，保留其余 risk_comment 内容
                cleaned_rc = rc.replace("物理引擎强制警报，置信度 1.0", "").replace(_PHYSICAL_ALERT_MARKER, "").strip()
                # 清理可能的残余标点
                cleaned_rc = cleaned_rc.rstrip("，,；;。.")
                diff["risk_comment"] = cleaned_rc
                logger.info("[PostProcess] 清除误合并的物理引擎警报: type=%s", diff_type)

        # ===================================================================
        # 【V3.1 终点钩子】坐标注入 —— 将空间坐标绑定到差异项
        # ===================================================================
        if enable_visual_localization and spatial_task is not None:
            try:
                spatial_index: Optional[SpatialIndex] = await asyncio.wait_for(
                    spatial_task, timeout=120.0
                )
                logger.info(
                    "[SpatialInjector] 索引就绪 blocks=%d，开始注入坐标...",
                    len(spatial_index.blocks) if spatial_index else 0,
                )
                final_report["differences"] = self._inject_visual_coordinates(
                    list(final_report.get("differences", []) or []), spatial_index
                )
                final_report["missing_items"] = self._inject_visual_coordinates(
                    list(final_report.get("missing_items", []) or []), spatial_index
                )
                logger.info("[SpatialInjector] 坐标注入完成")
            except Exception as exc:
                logger.warning("[SpatialInjector] 坐标注入失败（非阻断）: %s", exc)

        # ===================================================================
        # 组装完整结果
        # ===================================================================
        # 展平 BusinessMetric 嵌套对象，保证前端 API 类型兼容
        return flatten_business_metrics({
            "bid_text": bid_md[:50000],
            "contract_text": contract_md[:50000],
            "stage1_ingestion": {
                "bid_chars": len(bid_md),
                "contract_chars": len(contract_md),
            },
            "stage2_memory": {
                "bid_doc_id": bid_doc_id,
                "contract_doc_id": contract_doc_id,
                "bid_inserted": bid_ingest.get("inserted", 0),
                "contract_inserted": contract_ingest.get("inserted", 0),
            },
            # 汇总全链路 token 消耗（Stage3 + Agent A + Agent B + Agent C）
            "stage3_extraction": {
                "bid_info": bid_dict,
                "contract_info": contract_dict,
                "physical_alerts": physical_alerts,
                "token_usage": {
                    "prompt_tokens": (
                        bid_usage.get("prompt_tokens", 0)
                        + contract_usage.get("prompt_tokens", 0)
                        + baseline_usage.get("prompt_tokens", 0)
                        + agent_a_usage.get("prompt_tokens", 0)
                        + agent_b_usage.get("prompt_tokens", 0)
                        + (final_report.get("_token_usage", {}) or {}).get("prompt_tokens", 0)
                    ),
                    "completion_tokens": (
                        bid_usage.get("completion_tokens", 0)
                        + contract_usage.get("completion_tokens", 0)
                        + baseline_usage.get("completion_tokens", 0)
                        + agent_a_usage.get("completion_tokens", 0)
                        + agent_b_usage.get("completion_tokens", 0)
                        + (final_report.get("_token_usage", {}) or {}).get("completion_tokens", 0)
                    ),
                    "total_tokens": (
                        bid_usage.get("total_tokens", 0)
                        + contract_usage.get("total_tokens", 0)
                        + baseline_usage.get("total_tokens", 0)
                        + agent_a_usage.get("total_tokens", 0)
                        + agent_b_usage.get("total_tokens", 0)
                        + (final_report.get("_token_usage", {}) or {}).get("total_tokens", 0)
                    ),
                },
                # 分阶段 token 明细（供前端轨迹可视化）
                "stage_token_usage": {
                    "stage3_bid": bid_usage,
                    "stage3_contract": contract_usage,
                    "stage3_5_baseline": baseline_usage,
                    "stage4_agent_a": agent_a_usage,
                    "stage4_agent_b": agent_b_usage,
                    "stage5_agent_c": final_report.get("_token_usage", {}) or {},
                },
            },
            "stage4_committee": {
                "agent_a": (
                    [d if isinstance(d, dict) else d.model_dump() for d in agent_a_list]
                    if not isinstance(agent_a_raw, Exception)
                    else []
                ),
                "agent_b": (
                    [d if isinstance(d, dict) else d.model_dump() for d in agent_b_list]
                    if not isinstance(agent_b_raw, Exception)
                    else []
                ),
            },
            "stage5_supervisor": final_report,
        })


# ------------------------------------------------------------------------------
# 向后兼容的模块级便捷入口（保持旧调用方式可用，内部委托给默认实例）
# ------------------------------------------------------------------------------

_default_workflow: Optional[ContractReviewWorkflow] = None


async def process_contract_review(
    bid_pdf_path: str,
    contract_pdf_path: str,
    model_id: Optional[str] = None,
    price_tolerance: float = 0.0,
    required_clauses: Optional[List[str]] = None,
    custom_requirements: str = "",
    enable_visual_localization: bool = False,
    progress_callback: Optional[Callable[[int, str], Any]] = None,
) -> dict:
    """向后兼容的便捷函数，内部使用默认 DI 实例。"""
    global _default_workflow
    if _default_workflow is None:
        _default_workflow = ContractReviewWorkflow()
    return await _default_workflow.process_contract_review(
        bid_pdf_path,
        contract_pdf_path,
        model_id=model_id,
        price_tolerance=price_tolerance,
        required_clauses=required_clauses,
        custom_requirements=custom_requirements,
        enable_visual_localization=enable_visual_localization,
        progress_callback=progress_callback,
    )
