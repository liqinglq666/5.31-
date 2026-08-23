"""
app/application/tasks.py
------------------------
后台任务服务，封装五阶段合同审查流水线的执行与状态更新逻辑。
"""

import asyncio
import logging
import time

from app.crud.crud_task import update_task_db
from app.core.database import db_session
from app.application.workflows.contract_review import process_contract_review
from app.infrastructure.llm.dynamic_config import get_cached_active_model
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

# 批量更新窗口：相同任务在 N 秒内多次调 _progress，只写最后一次
_PROGRESS_BATCH_SECONDS = 5.0
_progress_locks: dict[str, asyncio.Lock] = {}
_progress_timers: dict[str, asyncio.Task] = {}

# 运行中任务注册表（支持取消）
_running_tasks: dict[str, asyncio.Task] = {}


async def cancel_compare_task(task_id: str) -> bool:
    """取消正在运行的比对任务。

    Returns:
        True 表示成功发起取消请求；False 表示任务不存在或已结束。
    """
    task = _running_tasks.get(task_id)
    if task is None or task.done():
        return False
    task.cancel()
    # 等待一小段时间让任务有机会捕获 CancelledError 并清理
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    return True

# ---------------------------------------------------------------------------
# missing_items 清洗工具
# ---------------------------------------------------------------------------

_NEGATIVE_KEYWORDS = (
    "未提及", "未约定", "无相关", "未明确", "未列明",
    "无约定", "未涉及", "不存在", "未规定", "未见",
)

_EMPTY_VALS = {"", "—", "-", "null", "none", "（合同中未找到）", "（采购结果中有）"}


def _is_empty_text(text: str) -> bool:
    t = text.strip()
    if not t or t in _EMPTY_VALS:
        return True
    if len(t) < 8 and any(k in t for k in _NEGATIVE_KEYWORDS):
        return True
    return False


def _clean_missing_items(missing_items: list) -> list:
    """清洗 Agent C 输出的 missing_items，抹杀 false positive。

    真正的 missing_item 必须同时满足：
    1. 采购结果侧有确凿原文约定（original_text 非空、有实质内容、不含否定词）
    2. 合同侧确实缺失（contract_text 为空、含否定词、或长度极短）
    3. 不能是双向均未提及（疑罪从无）
    """
    cleaned: list = []
    for m in missing_items:
        if not isinstance(m, dict):
            continue
        orig = str(m.get("original_text") or "").strip()
        cont = str(m.get("contract_text") or "").strip()
        desc = str(m.get("description") or "").strip()

        # 1. 抹杀双向空（疑罪从无）
        if _is_empty_text(orig) and _is_empty_text(cont):
            logger.info("[CleanMissing] 抹杀双向空缺失: %s", desc[:60])
            continue

        # 2. 采购结果侧必须确有约定
        if not orig or len(orig) < 5 or any(k in orig for k in _NEGATIVE_KEYWORDS):
            logger.info("[CleanMissing] 抹杀 orig 无实质内容: %s", desc[:60])
            continue

        # 3. 合同侧必须确实缺失（若合同侧有实质条款文本，则不是缺失，可能是差异或新增）
        if cont and len(cont) > 15 and not any(k in cont for k in _NEGATIVE_KEYWORDS):
            logger.info("[CleanMissing] 抹杀 contract 有实质内容: %s", desc[:60])
            continue

        cleaned.append(m)

    if len(cleaned) != len(missing_items):
        logger.info(
            "[CleanMissing] %d -> %d (过滤 %d 条 false positive)",
            len(missing_items),
            len(cleaned),
            len(missing_items) - len(cleaned),
        )
    return cleaned


async def process_compare_task(
    task_id: str,
    bid_path: str,
    contract_path: str,
    model_id: str | None = None,
    price_tolerance: float = 0.0,
    required_clauses: list[str] | None = None,
    custom_requirements: str = "",
    enable_visual_localization: bool = False,
) -> None:
    """
    后台执行的五阶段合同审查流水线。
    1. 高保真 PDF 解析（Docling）
    2. 向量记忆构建（Milvus + RAPTOR）
    3. 结构化提取 + 物理引擎验算
    4. 商务 Agent A + 法务 Agent B 并发审查
    5. 风控总管 Agent C（CoVe 终审）
    结果持久化到 PostgreSQL。
    """

    # 注册当前任务，支持外部取消
    current_task = asyncio.current_task()
    if current_task is not None:
        _running_tasks[task_id] = current_task

    # 批量进度更新：相同任务在 _PROGRESS_BATCH_SECONDS 窗口内多次调用，
    # 仅触发一次 DB 写入，降低长耗时工作流对连接池的占用。
    _pending: dict[str, dict] = {}

    def _schedule_flush() -> None:
        """调度延迟 flush；若已存在定时器则重置。"""
        old_task = _progress_timers.pop(task_id, None)
        if old_task is not None:
            old_task.cancel()
        _progress_timers[task_id] = asyncio.create_task(_delayed_flush())

    async def _delayed_flush() -> None:
        await asyncio.sleep(_PROGRESS_BATCH_SECONDS)
        await _flush_now()

    async def _flush_now() -> None:
        """立即将 pending 进度写入 DB。"""
        state = _pending.pop(task_id, None)
        if state is None:
            return
        async with db_session() as db:
            try:
                await update_task_db(db, task_id=task_id, **state)
            except Exception as exc:
                await db.rollback()
                logger.warning("[BackgroundTask] 批量更新任务状态失败 task_id=%s: %s", task_id, exc)

    async def _progress(progress: int, message: str, process_mode: str | None = None, force: bool = False) -> None:
        kwargs: dict = {
            "status": "processing",
            "message": message,
            "progress": progress,
        }
        if process_mode is not None:
            kwargs["process_mode"] = process_mode
        _pending[task_id] = kwargs
        if force:
            old_task = _progress_timers.pop(task_id, None)
            if old_task is not None:
                old_task.cancel()
            await _flush_now()
        else:
            _schedule_flush()

    await _progress(5, "任务开始执行...", "FULL_PIPELINE")

    # 记录任务执行起始时间与当前激活模型（避免执行中途切换模型导致记录失真）
    start_time = time.time()
    active_model = get_cached_active_model()
    task_model_name = active_model["model_name"] if active_model else "unknown"

    try:
        await _progress(20, "正在进行高保真 PDF 解析与记忆构建...")

        # 包装进度回调，适配 workflow 的 (int, str) 签名
        async def _workflow_progress(p: int, msg: str) -> None:
            await _progress(p, msg)

        result = await process_contract_review(
            bid_path,
            contract_path,
            model_id=model_id,
            price_tolerance=price_tolerance,
            required_clauses=required_clauses,
            custom_requirements=custom_requirements,
            enable_visual_localization=enable_visual_localization,
            progress_callback=_workflow_progress,
        )

        # 转换为前端兼容格式
        stage3 = result.get("stage3_extraction", {})
        stage4 = result.get("stage4_committee", {})
        stage5 = result.get("stage5_supervisor", {})

        bid_info = stage3.get("bid_info", {})
        contract_info = stage3.get("contract_info", {})

        # 清洗 missing_items：抹杀 false positive（采购结果中本来就没有的条款，不算合同缺失）
        missing_items = _clean_missing_items(list(stage5.get("missing_items", []) or []))

        # 给 missing_items 补充 type 字段（前端兼容）
        for m in missing_items:
            if isinstance(m, dict) and not m.get("type"):
                clause_name = m.get("clause_name", "条款")
                m["type"] = f"【{clause_name}】缺失"

        # 分阶段 token 明细
        stage_tokens = stage3.get("stage_token_usage", {})
        bid_tokens = stage_tokens.get("stage3_bid", {})
        contract_tokens = stage_tokens.get("stage3_contract", {})
        agent_a_tokens = stage_tokens.get("stage4_agent_a", {})
        agent_b_tokens = stage_tokens.get("stage4_agent_b", {})
        agent_c_tokens = stage_tokens.get("stage5_agent_c", {})

        # 构造 agent_traces（供前端展示协作轨迹）
        agent_traces = [
            {
                "stage": 1,
                "agent": "物理摄入 (Docling)",
                "action": "完成高保真 PDF 解析与 Markdown 输出",
                "description": "将采购结果与正式合同 PDF 通过 Docling 视觉模型解析为结构化 Markdown，保留表格与标题层级。",
                "status": "success",
                "detail": {
                    "bid_chars": result.get("stage1_ingestion", {}).get("bid_chars", 0),
                    "contract_chars": result.get("stage1_ingestion", {}).get("contract_chars", 0),
                },
            },
            {
                "stage": 2,
                "agent": "记忆构建 (Milvus)",
                "action": "完成语义切块与向量入库",
                "description": "按 Markdown 标题层级切分语义块，生成 384 维 Embedding 并写入 Milvus，构建可检索的拓扑记忆层。",
                "status": "success",
                "detail": {
                    "bid_inserted": result.get("stage2_memory", {}).get("bid_inserted", 0),
                    "contract_inserted": result.get("stage2_memory", {}).get("contract_inserted", 0),
                },
            },
            {
                "stage": 3,
                "agent": "结构化提取 (LLM)",
                "action": "完成合同信息提取与物理引擎预检",
                "description": "调用 LLM 提取供应商、金额、付款节点等结构化字段；物理引擎逐项验算 单价×数量=小计。",
                "status": "success",
                "detail": {
                    "bid_tokens": bid_tokens.get("total_tokens", 0),
                    "contract_tokens": contract_tokens.get("total_tokens", 0),
                    "physical_alert_count": len(stage3.get("physical_alerts", [])),
                    "hybrid_extraction": True,
                },
            },
            {
                "stage": 4,
                "agent": "商务审计 (Agent A)",
                "action": "完成商务条款比对",
                "description": "比对采购结果与合同中的金额、付款节点、交货期、质保期等商务条款，标记数值差异与缺失项。",
                "status": "success",
                "detail": {
                    "diff_count": len(stage4.get("agent_a", [])),
                    "tokens": agent_a_tokens.get("total_tokens", 0),
                    "tool_calls": agent_a_tokens.get("tool_calls", 0),
                    "iterations": agent_a_tokens.get("iterations", 0),
                    "context_pruned": agent_a_tokens.get("pruned", False),
                },
            },
            {
                "stage": 5,
                "agent": "法务审计 (Agent B)",
                "action": "完成法务条款审查",
                "description": "基于 Milvus GraphRAG 检索合同上下文，审查违约责任、知识产权、保密义务、争议解决等法务条款。",
                "status": "success",
                "detail": {
                    "diff_count": len(stage4.get("agent_b", [])),
                    "tokens": agent_b_tokens.get("total_tokens", 0),
                    "tool_calls": agent_b_tokens.get("tool_calls", 0),
                    "iterations": agent_b_tokens.get("iterations", 0),
                    "context_pruned": agent_b_tokens.get("pruned", False),
                },
            },
            {
                "stage": 6,
                "agent": "风控总管 (Agent C)",
                "action": "完成终审与置信度评分",
                "description": "综合 Agent A（商务）、Agent B（法务）与物理引擎的审查结果，执行 CoVe 防幻觉核实，输出最终风险等级与置信度。",
                "status": "success",
                "detail": {
                    "final_risk_level": stage5.get("risk_level", "low"),
                    "confidence_score": stage5.get("confidence_score", 0.0),
                    "tokens": agent_c_tokens.get("total_tokens", 0),
                    "cove_verification_length": len(stage5.get("_cove_verification", "")),
                },
            },
        ]

        # 物理引擎预检警报（传给前端展示）
        physical_alerts = list(stage3.get("physical_alerts", []) or [])

        frontend_result = {
            "bid_info": bid_info,
            "contract_info": contract_info,
            "comparison": {
                "risk_level": stage5.get("risk_level", "low"),
                "confidence_score": stage5.get("confidence_score", 0.0),
                "differences": list(stage5.get("differences", []) or []),
                "missing_items": missing_items,
                "matches": list(stage5.get("matches", []) or []),
                "review_comments": stage5.get("review_comments", ""),
                "parsed_contract_text": result.get("contract_text", ""),
                "agent_traces": agent_traces,
                "physical_alerts": physical_alerts,
            },
            "process_mode": "FULL_PIPELINE",
            "financial_info": {},
            "token_usage": stage3.get("token_usage", {}),
        }

        supplier_name = ""
        if isinstance(bid_info, dict):
            supplier_name = bid_info.get("vendor_name", "")

        # 强制刷出所有 pending 进度，再写入最终完成状态
        await _flush_now()
        async with db_session() as db:
            try:
                await update_task_db(
                    db,
                    task_id=task_id,
                    status="completed",
                    message="比对任务已完成",
                    progress=100,
                    result=frontend_result,
                    process_mode="FULL_PIPELINE",
                    supplier_name=supplier_name,
                    model_name=task_model_name,
                    processing_seconds=int(time.time() - start_time),
                )
                # 更新供应商画像（记忆积累）
                if supplier_name:
                    missing_clauses: list[str] = []
                    if isinstance(result, dict):
                        comparison = result.get("comparison") or {}
                        missing_items = comparison.get("missing_items", [])
                        if isinstance(missing_items, list):
                            missing_clauses = [
                                str(m.get("description", ""))
                                for m in missing_items
                                if isinstance(m, dict) and m.get("description")
                            ]
                    risk_level = "low"
                    if isinstance(result, dict):
                        comparison = result.get("comparison") or {}
                        risk_level = comparison.get("risk_level", "low")
                    memory_service = MemoryService(db)
                    await memory_service.upsert_supplier_profile(
                        supplier_name, missing_clauses, risk_level
                    )
                    await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.warning("[BackgroundTask] 更新完成状态失败 task_id=%s: %s", task_id, exc)

    except asyncio.CancelledError:
        logger.info("[BackgroundTask] 任务被取消 task_id=%s", task_id)
        # 取消可能存在的延迟定时器
        old_task = _progress_timers.pop(task_id, None)
        if old_task is not None:
            old_task.cancel()
        _pending.pop(task_id, None)
        async with db_session() as db:
            try:
                await update_task_db(
                    db,
                    task_id=task_id,
                    status="cancelled",
                    message="任务已取消",
                    progress=0,
                    model_name=task_model_name,
                    processing_seconds=int(time.time() - start_time),
                )
            except Exception as inner_exc:
                await db.rollback()
                logger.warning("[BackgroundTask] 更新取消状态失败 task_id=%s: %s", task_id, inner_exc)
        raise  # 重新抛出 CancelledError，让 asyncio 正常回收任务

    except Exception as exc:
        logger.exception("[BackgroundTask] 五阶段流水线执行失败 task_id=%s", task_id)
        # 取消可能存在的延迟定时器，防止失败后再写 processing 状态
        old_task = _progress_timers.pop(task_id, None)
        if old_task is not None:
            old_task.cancel()
        _pending.pop(task_id, None)
        async with db_session() as db:
            try:
                await update_task_db(
                    db,
                    task_id=task_id,
                    status="failed",
                    message=f"任务执行失败: {str(exc)}",
                    progress=0,
                    model_name=task_model_name,
                    processing_seconds=int(time.time() - start_time),
                )
            except Exception as inner_exc:
                await db.rollback()
                logger.warning("[BackgroundTask] 更新失败状态失败 task_id=%s: %s", task_id, inner_exc)

    finally:
        # 任务结束（成功/失败/取消），从注册表中移除
        _running_tasks.pop(task_id, None)
