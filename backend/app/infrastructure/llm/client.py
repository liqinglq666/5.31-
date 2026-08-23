"""
core/llm_client.py
------------------
基于原生 openai.AsyncOpenAI 的统一 LLM 客户端。
根据 model_id 动态选择 api_key / base_url，零冗余代码。
所有模型均兼容 OpenAI 接口规范，故只需一套客户端逻辑。
"""

import asyncio
import json
import logging
from typing import Dict, Optional, AsyncIterable, List, Callable, Any, Awaitable

import httpx
from openai import AsyncOpenAI, RateLimitError, AuthenticationError, BadRequestError

from app.core.config import settings
from app.infrastructure.llm.retry import retry_with_exponential_backoff
from app.infrastructure.llm.dynamic_config import (
    get_cached_model_config,
    get_default_model_id,
)

logger = logging.getLogger(__name__)

# 客户端缓存：按 (model_id, base_url) 复用 AsyncOpenAI 实例，避免高频重建连接池
_CLIENT_CACHE: Dict[str, AsyncOpenAI] = {}

# 全局限流：同时最多 10 个 LLM 并发调用，防止商业 API 触发 429
_LLM_CALL_SEMAPHORE = asyncio.Semaphore(10)

# Fallback 优先级：当主模型额度耗尽或认证失败时，按此顺序自动切换
_FALLBACK_CHAIN = [
    "qwen-max",
    "deepseek-chat",
    "glm-5-plus",
    "doubao-pro-32k",
]


def _get_db_model_info(model_id: str) -> dict:
    """仅从数据库缓存获取模型元信息，用于日志与 API 调用。"""
    db_cfg = get_cached_model_config(model_id)
    if db_cfg:
        return {
            "id": db_cfg["model_name"],
            "provider": db_cfg["provider"],
            "base_url": db_cfg.get("base_url", ""),
        }
    return {"id": model_id, "provider": "unknown", "base_url": ""}


def _resolve_api_model_id(model_id: str) -> str:
    """获取实际用于 API 调用的模型 ID。
    如果数据库中配置了 api_model_id，优先使用；否则回退到 model_name。
    """
    db_cfg = get_cached_model_config(model_id)
    if db_cfg:
        api_id = db_cfg.get("api_model_id")
        if api_id:
            return api_id
    return model_id


def create_openai_client(model_id: Optional[str] = None) -> AsyncOpenAI:
    """动态实例化 AsyncOpenAI 客户端（带缓存）。仅使用数据库动态配置。"""
    model_id = model_id or get_default_model_id()

    db_cfg = get_cached_model_config(model_id)
    if db_cfg and db_cfg.get("api_key"):
        cache_key = f"db:{db_cfg['model_name']}@{db_cfg['base_url']}"
        if cache_key not in _CLIENT_CACHE:
            _CLIENT_CACHE[cache_key] = AsyncOpenAI(
                api_key=db_cfg["api_key"],
                base_url=db_cfg["base_url"] or None,
                timeout=httpx.Timeout(connect=10, read=120, write=30, pool=30),
            )
            logger.info("[LLM] Created new DB-driven client for %s", cache_key)
        return _CLIENT_CACHE[cache_key]

    raise ValueError(
        f"模型 '{model_id}' 未在数据库中配置。请前往系统管理 → 模型管理录入配置。"
    )


def _pick_fallback(excluded: set[str]) -> Optional[str]:
    """从 fallback 链中选一个尚未尝试且数据库中配置了 api_key 的模型。"""
    for m in _FALLBACK_CHAIN:
        if m in excluded:
            continue
        db_cfg = get_cached_model_config(m)
        if db_cfg and db_cfg.get("api_key"):
            return m
    return None


def _get_model_temperature(model_id: str) -> float:
    """从数据库缓存读取模型的采样温度，默认 0.0。"""
    db_cfg = get_cached_model_config(model_id)
    if db_cfg:
        try:
            return float(db_cfg.get("temperature", "0.0") or "0.0")
        except (ValueError, TypeError):
            pass
    return 0.0


@retry_with_exponential_backoff(max_retries=3, base_delay=1.0)
async def chat_completion(
    messages: List[dict],
    model_id: Optional[str] = None,
    temperature: float = -1.0,
    response_format: Optional[dict] = None,
    max_tokens: Optional[int] = None,
    tools: Optional[List[dict]] = None,
    tool_choice: Optional[str] = None,
) -> tuple[str, dict]:
    """非流式对话，返回 (完整文本, token_usage)。支持 JSON mode 结构化输出。

    当主模型触发 RateLimitError / AuthenticationError 时，自动按 _FALLBACK_CHAIN
    切换到备用模型，避免单点额度耗尽导致任务整体失败。
    """
    resolved_model = model_id or get_default_model_id()
    if temperature < 0:
        temperature = _get_model_temperature(resolved_model)
    tried = {resolved_model}

    while True:
        client = create_openai_client(resolved_model)
        info = _get_db_model_info(resolved_model)
        logger.info(
            "[LLM] chat_completion -> model=%s provider=%s base_url=%s temp=%s",
            info["id"], info["provider"], info["base_url"], temperature,
        )
        kwargs: dict = {}
        if response_format:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        actual_model = _resolve_api_model_id(resolved_model)
        try:
            async with _LLM_CALL_SEMAPHORE:
                response = await client.chat.completions.create(
                    model=actual_model,
                    messages=messages,
                    temperature=temperature,
                    **kwargs,
                )
        except BadRequestError as exc:
            err_msg = str(exc).lower()
            if "temperature" in err_msg:
                logger.warning(
                    "[LLM] Model %s rejected temperature=%s, retrying with temperature=1",
                    actual_model, temperature,
                )
                async with _LLM_CALL_SEMAPHORE:
                    response = await client.chat.completions.create(
                        model=actual_model,
                        messages=messages,
                        temperature=1,
                        **kwargs,
                    )
            else:
                raise
        except (RateLimitError, AuthenticationError) as exc:
            fallback = _pick_fallback(tried)
            if fallback:
                logger.warning(
                    "[LLM] %s 触发 %s，自动降级到 %s",
                    resolved_model, type(exc).__name__, fallback,
                )
                resolved_model = fallback
                tried.add(resolved_model)
                continue
            logger.error("[LLM] 所有模型均已耗尽或认证失败: %s", exc)
            raise

        content = response.choices[0].message.content or ""
        usage = {
            "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            "completion_tokens": getattr(response.usage, "completion_tokens", 0) if response.usage else 0,
            "total_tokens": getattr(response.usage, "total_tokens", 0) if response.usage else 0,
        }
        logger.info("[LLM] usage=%s", usage)
        return content, usage


async def _inner_stream(
    messages: List[dict],
    model_id: str,
    temperature: float,
    usage_callback: Optional[Callable[[dict], None]],
) -> AsyncIterable[str]:
    """流式内核（供 stream_chat_completion 重试/fallback 时复用）。"""
    if temperature < 0:
        temperature = _get_model_temperature(model_id)
    client = create_openai_client(model_id)
    info = _get_db_model_info(model_id)
    logger.info(
        "[LLM] stream_chat_completion -> model=%s provider=%s base_url=%s temp=%s",
        info["id"], info["provider"], info["base_url"], temperature,
    )
    actual_model = _resolve_api_model_id(model_id)
    try:
        async with _LLM_CALL_SEMAPHORE:
            response = await client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=temperature,
                stream=True,
                stream_options={"include_usage": True},
            )
    except BadRequestError as exc:
        err_msg = str(exc).lower()
        if "temperature" in err_msg:
            logger.warning(
                "[LLM] Model %s rejected temperature=%s in stream, retrying with temperature=1",
                actual_model, temperature,
            )
            async with _LLM_CALL_SEMAPHORE:
                response = await client.chat.completions.create(
                    model=actual_model,
                    messages=messages,
                    temperature=1,
                    stream=True,
                    stream_options={"include_usage": True},
                )
        else:
            raise
    usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    async for chunk in response:
        if chunk.usage:
            usage_data["prompt_tokens"] = getattr(chunk.usage, "prompt_tokens", 0)
            usage_data["completion_tokens"] = getattr(chunk.usage, "completion_tokens", 0)
            usage_data["total_tokens"] = getattr(chunk.usage, "total_tokens", 0)
            continue
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta
    if usage_callback:
        usage_callback(usage_data)


async def stream_chat_completion(
    messages: List[dict],
    model_id: Optional[str] = None,
    temperature: float = -1.0,
    usage_callback: Optional[Callable[[dict], None]] = None,
) -> AsyncIterable[str]:
    """流式对话，逐块 yield 文本内容（SSE 兼容）。支持自动 fallback。

    当主模型触发 RateLimitError / AuthenticationError 时，自动按 _FALLBACK_CHAIN
    切换到备用模型。fallback 切换发生在第一次 yield 之前，对调用方透明。
    """
    resolved_model = model_id or get_default_model_id()
    tried = {resolved_model}

    while True:
        try:
            async for text in _inner_stream(
                messages, resolved_model, temperature, usage_callback
            ):
                yield text
            return
        except (RateLimitError, AuthenticationError) as exc:
            fallback = _pick_fallback(tried)
            if fallback:
                logger.warning(
                    "[LLM] %s 触发 %s，自动降级到 %s",
                    resolved_model, type(exc).__name__, fallback,
                )
                resolved_model = fallback
                tried.add(resolved_model)
                continue
            logger.error("[LLM] 所有模型均已耗尽或认证失败: %s", exc)
            raise


# -----------------------------------------------------------------------------
# Unified Tool-Calling Executor with Context Pruning & Token Tracking
# -----------------------------------------------------------------------------

# 安全边界：当消息总字符数超过此阈值时触发 pair pruning
_CONTEXT_PRUNE_THRESHOLD = 28000
# 降级安全余量：保留给最终 fallback generation 的字符预算
_FALLBACK_RESERVE = 15000


def _prune_messages(messages: list) -> None:
    """Backward pair pruning：当消息总字符数超过阈值时，从最旧开始删除
    assistant（含 tool_calls）+ 后续 tool 消息对，直到降到安全范围。"""
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    if total_chars <= _CONTEXT_PRUNE_THRESHOLD:
        return

    # 识别所有 assistant+tool 对的起始索引（assistant 消息位置）
    assistant_indices: list[int] = []
    for idx, m in enumerate(messages):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            assistant_indices.append(idx)

    # backward pruning：从最旧的对开始删除（reversed range）
    for assistant_idx in reversed(assistant_indices):
        if total_chars <= _CONTEXT_PRUNE_THRESHOLD:
            break
        delete_start = assistant_idx
        delete_end = assistant_idx + 1
        while delete_end < len(messages) and messages[delete_end].get("role") == "tool":
            delete_end += 1

        removed_chars = sum(
            len(str(messages[i].get("content", ""))) for i in range(delete_start, delete_end)
        )
        del messages[delete_start:delete_end]
        total_chars -= removed_chars
        logger.info(
            "[ToolLoop] Pruned assistant+tools pair at idx=%d (%d messages, %d chars)",
            assistant_idx,
            delete_end - delete_start,
            removed_chars,
        )

    # 如果删完所有 tool 对仍然过长，保留 system + 最近 user + 最近 assistant
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    if total_chars > _CONTEXT_PRUNE_THRESHOLD:
        logger.warning(
            "[ToolLoop] After pruning all tool pairs, context still overflow. Stripping to essential."
        )
        essential: list[dict] = []
        for m in messages:
            if m.get("role") == "system":
                essential.append(m)
        for m in reversed(messages):
            if m.get("role") == "user":
                essential.append(m)
                break
        for m in reversed(messages):
            if m.get("role") == "assistant" and not m.get("tool_calls"):
                essential.append(m)
                break
        messages[:] = essential


def _build_fallback_system_msg() -> dict:
    """构造上下文溢出时的降级 system 消息。"""
    return {
        "role": "system",
        "content": (
            "【系统警告】由于历史工具调用结果过长，部分早期上下文已被修剪。"
            "请你基于现有信息，直接输出最终结论，不要再发起新的工具调用。"
            "如果信息不足以完成判断，请在输出中明确标注'信息不足，建议人工复核'。"
        ),
    }


async def execute_tool_loop_with_tracking(
    messages: list[dict],
    tool_schemas: list[dict],
    tool_executor: Callable[[str, dict], Any],
    *,
    model_id: str | None = None,
    max_iterations: int = 25,
    intermediate_max_tokens: int = 2048,
    attention_injection_callback: Callable[[int, list[dict]], None] | None = None,
) -> tuple[str, dict, list[dict]]:
    """统一工具调用执行循环，支持累积 Token 追踪、上下文修剪与降级生成。

    当上下文窗口溢出时，采用 backward pair pruning（从最旧的 assistant+tool 对开始删除）。
    如果修剪后仍然过长，注入降级 system 消息，要求 LLM 直接输出最终结论而不发起新工具调用。

    Args:
        messages: 初始消息列表（会被原地修改）。
        tool_schemas: OpenAI Function Calling 格式的工具 Schema 列表。
        tool_executor: 工具执行函数，签名为 (tool_name: str, args: dict) -> result: Any。
        model_id: 可选，指定底层 LLM 模型 ID。
        max_iterations: 最大迭代轮数。
        intermediate_max_tokens: 每轮中间调用的 max_tokens。
        attention_injection_callback: 可选，在每轮迭代前调用，
            签名为 (iteration: int, messages: list[dict]) -> None，可原地注入注意力消息。

    Returns:
        (final_text, usage_accum, messages_trace)
        - final_text: LLM 最终回复文本。
        - usage_accum: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}。
        - messages_trace: 完整的对话轨迹（供审计与调试）。
    """
    resolved_model = model_id or get_default_model_id()
    client = create_openai_client(resolved_model)
    info = _get_db_model_info(resolved_model)
    tool_loop_temp = _get_model_temperature(resolved_model)

    usage_accum = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "tool_calls": 0,
        "iterations": 0,
        "pruned": False,
    }
    messages_trace: list[dict] = [dict(m) for m in messages]
    pruned_once = False

    # 重复查询检测：连续 2 轮发出完全相同的工具调用，则提前终止
    seen_tool_sigs: set[str] = set()
    repeat_streak = 0

    for iteration in range(1, max_iterations + 1):
        pre_prune_len = len(messages)
        _prune_messages(messages)
        _prune_messages(messages_trace)
        if len(messages) < pre_prune_len:
            pruned_once = True

        if attention_injection_callback is not None:
            attention_injection_callback(iteration, messages)
            attention_injection_callback(iteration, messages_trace)

        logger.info(
            "[ToolLoop] iteration %d/%d -> model=%s messages_len=%d",
            iteration,
            max_iterations,
            info["id"],
            len(messages),
        )

        # 检查是否已触发降级（消息被修剪到只剩 essential）
        has_been_pruned = len(messages) <= 3 and iteration > 1

        actual_model = _resolve_api_model_id(resolved_model)
        try:
            async with _LLM_CALL_SEMAPHORE:
                response = await client.chat.completions.create(
                    model=actual_model,
                    messages=messages,
                    temperature=tool_loop_temp,
                    max_tokens=intermediate_max_tokens,
                    tools=tool_schemas,
                    tool_choice="auto",
                )
        except BadRequestError as exc:
            err_msg = str(exc).lower()
            if "temperature" in err_msg:
                logger.warning(
                    "[ToolLoop] Model %s rejected temperature=%s in tool loop, retrying with temperature=1",
                    actual_model, tool_loop_temp,
                )
                async with _LLM_CALL_SEMAPHORE:
                    response = await client.chat.completions.create(
                        model=actual_model,
                        messages=messages,
                        temperature=1,
                        max_tokens=intermediate_max_tokens,
                        tools=tool_schemas,
                        tool_choice="auto",
                    )
            else:
                raise
        except Exception as exc:
            logger.exception("[ToolLoop] LLM call failed at iteration %d", iteration)
            raise

        if response.usage:
            usage_accum["prompt_tokens"] += getattr(response.usage, "prompt_tokens", 0)
            usage_accum["completion_tokens"] += getattr(response.usage, "completion_tokens", 0)
            usage_accum["total_tokens"] += getattr(response.usage, "total_tokens", 0)

        msg = response.choices[0].message
        usage_accum["iterations"] = iteration

        # Case 1: 无 tool_calls -> 最终答案
        if not getattr(msg, "tool_calls", None):
            logger.info("[ToolLoop] No tool calls in response, finishing at iteration %d.", iteration)
            usage_accum["pruned"] = pruned_once
            return msg.content or "", usage_accum, messages_trace

        # Case 2: 有 tool_calls -> 执行工具
        tool_call_count = len(msg.tool_calls)
        usage_accum["tool_calls"] += tool_call_count

        assistant_msg = {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        }
        # DeepSeek reasoning 模型要求多轮对话必须回传 reasoning_content
        reasoning_content = getattr(msg, "reasoning_content", None)
        if reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content
        messages.append(assistant_msg)
        messages_trace.append(dict(assistant_msg))

        for tc in msg.tool_calls:
            func_name = tc.function.name
            raw_args = tc.function.arguments
            tool_call_id = tc.id

            logger.info(
                "[ToolLoop] Tool call -> name=%s args=%s id=%s",
                func_name,
                raw_args,
                tool_call_id,
            )

            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError as exc:
                result = {"error": f"Invalid JSON arguments: {exc}"}
            else:
                try:
                    result = tool_executor(func_name, args)
                    if asyncio.iscoroutine(result):
                        result = await result
                except Exception as exc:
                    result = {"error": f"Tool execution failed: {exc}"}

            result_str = json.dumps(result, ensure_ascii=False)
            tool_msg = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result_str,
            }
            messages.append(tool_msg)
            messages_trace.append(dict(tool_msg))
            logger.info("[ToolLoop] Tool result -> id=%s len=%d", tool_call_id, len(result_str))

        # 提前终止：连续 2 轮发出完全相同的工具调用，说明 LLM 在重复搜索，强制收网
        current_sigs = {f"{tc.function.name}:{tc.function.arguments}" for tc in msg.tool_calls}
        if current_sigs and current_sigs.issubset(seen_tool_sigs):
            repeat_streak += 1
            logger.warning(
                "[ToolLoop] Repeated tool calls detected (streak=%d/2) at iteration %d",
                repeat_streak, iteration,
            )
            if repeat_streak >= 2:
                logger.warning("[ToolLoop] Early termination triggered after 2 consecutive repeated rounds.")
                break
        else:
            repeat_streak = 0
            seen_tool_sigs.update(current_sigs)

        # 如果已触发降级，追加 system 警告
        if has_been_pruned and iteration < max_iterations:
            fallback_msg = _build_fallback_system_msg()
            messages.append(fallback_msg)
            messages_trace.append(dict(fallback_msg))
            logger.warning("[ToolLoop] Context pruned to essential, injected fallback warning.")

    if iteration >= max_iterations:
        logger.warning("[ToolLoop] Max iterations (%d) reached, forcing return.", max_iterations)
    else:
        logger.warning("[ToolLoop] Early termination, forcing return.")

    usage_accum["pruned"] = pruned_once
    return msg.content or "", usage_accum, messages_trace
