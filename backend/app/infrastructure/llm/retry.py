"""
infrastructure/llm/retry.py
--------------------------
LLM 调用韧性策略：重试、熔断、降级。

设计原则：
- 与具体 LLM 客户端解耦，以装饰器/包装器形式提供。
- 默认自动挂载到 chat_completion / stream_chat_completion，对业务层零感知。
"""

import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from openai import (
    AuthenticationError,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    APIStatusError,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# 1. 指数退避重试
# ---------------------------------------------------------------------------

DEFAULT_RETRYABLE_EXCEPTIONS = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    APIStatusError,
)


def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = DEFAULT_RETRYABLE_EXCEPTIONS,
) -> Callable[[F], F]:
    """装饰器：对指定的可重试异常执行指数退避重试。

    - RateLimitError / Timeout / ConnectionError：自动重试
    - AuthenticationError：立即失败（不重试）
    - 其他异常：立即失败
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except AuthenticationError:
                    logger.error("[Retry] AuthenticationError on attempt %d/%d — not retrying.", attempt, max_retries)
                    raise
                except retryable_exceptions as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                        logger.warning(
                            "[Retry] %s on attempt %d/%d, sleeping %.1fs then retrying...",
                            type(exc).__name__,
                            attempt,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "[Retry] %s on attempt %d/%d — max retries exceeded.",
                            type(exc).__name__,
                            attempt,
                            max_retries,
                        )
            raise last_exception  # type: ignore[misc]

        return async_wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# 2. 熔断器 (Circuit Breaker)
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """简易熔断器。

    状态机：
    - CLOSED:   正常通行，连续失败计数。
    - OPEN:     熔断开启，所有调用直接抛异常，经过 cooldown 后进入 HALF_OPEN。
    - HALF_OPEN: 允许一次探测调用，成功则 CLOSED，失败则 OPEN。
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._state = "CLOSED"
        self._failures = 0
        self._last_failure_time: Optional[float] = None

    def _can_attempt(self) -> bool:
        if self._state == "CLOSED":
            return True
        if self._state == "OPEN":
            assert self._last_failure_time is not None
            if time.time() - self._last_failure_time >= self.cooldown_seconds:
                self._state = "HALF_OPEN"
                logger.info("[CircuitBreaker] Transition OPEN -> HALF_OPEN")
                return True
            return False
        # HALF_OPEN
        return True

    def record_success(self) -> None:
        self._failures = 0
        if self._state in ("OPEN", "HALF_OPEN"):
            self._state = "CLOSED"
            logger.info("[CircuitBreaker] Transition %s -> CLOSED", self._state)

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self.failure_threshold:
            if self._state != "OPEN":
                self._state = "OPEN"
                logger.error(
                    "[CircuitBreaker] Transition %s -> OPEN (failures=%d)",
                    self._state,
                    self._failures,
                )

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if not self._can_attempt():
            raise RuntimeError("Circuit breaker is OPEN — LLM service temporarily unavailable")
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


# ---------------------------------------------------------------------------
# 3. 模型降级注册表
# ---------------------------------------------------------------------------

class FallbackRegistry:
    """当指定模型不可用时，自动降级到默认模型。"""

    def __init__(self, default_model_id: Optional[str] = None) -> None:
        self.default_model_id = default_model_id

    def resolve(self, requested_model_id: Optional[str]) -> str:
        # 目前简化实现：直接返回默认模型
        # 未来可扩展为根据健康检查动态选择可用模型
        return requested_model_id or self.default_model_id or "gpt-4o"


# ---------------------------------------------------------------------------
# 4. 默认实例（供 client.py 挂载）
# ---------------------------------------------------------------------------

circuit_breaker = CircuitBreaker()
fallback_registry: Optional[FallbackRegistry] = None


def init_fallback_registry(default_model_id: str) -> None:
    global fallback_registry
    fallback_registry = FallbackRegistry(default_model_id)
