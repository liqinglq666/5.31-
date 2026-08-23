"""
core/exceptions.py
------------------
统一异常体系（Unified Exception Hierarchy）。

设计原则：
- 所有业务异常均继承自 BankAIError，携带 code / message / status_code。
- 全局异常处理器捕获 BankAIError 子类后，自动序列化为统一响应格式。
- 未知异常（非 BankAIError）统一包装为 500，避免敏感信息泄漏。
"""

from typing import Optional, Any, Dict


class BankAIError(Exception):
    """全栈统一异常基类。

    Attributes:
        code: 业务错误码（前端用于分类提示）。
        message: 用户友好的错误描述。
        status_code: HTTP 状态码。
        detail: 供调试的附加信息（生产环境可选择不暴露）。
    """

    def __init__(
        self,
        message: str,
        code: int = 500,
        status_code: int = 500,
        detail: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典，供 FastAPI 异常处理器直接返回。"""
        payload = {
            "code": self.code,
            "message": self.message,
            "data": None,
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


# ---------------------------------------------------------------------------
# 认证与授权
# ---------------------------------------------------------------------------

class AuthError(BankAIError):
    """认证失败（未登录、Token 过期、Token 无效）。"""

    def __init__(self, message: str = "认证失败，请重新登录", detail: Optional[Any] = None) -> None:
        super().__init__(message, code=401, status_code=401, detail=detail)


class PermissionDeniedError(BankAIError):
    """权限不足（已登录但无操作权限）。"""

    def __init__(self, message: str = "权限不足", detail: Optional[Any] = None) -> None:
        super().__init__(message, code=403, status_code=403, detail=detail)


# ---------------------------------------------------------------------------
# 参数与业务校验
# ---------------------------------------------------------------------------

class ValidationError(BankAIError):
    """请求参数校验失败。"""

    def __init__(self, message: str = "请求参数错误", detail: Optional[Any] = None) -> None:
        super().__init__(message, code=422, status_code=422, detail=detail)


class NotFoundError(BankAIError):
    """资源不存在。"""

    def __init__(self, message: str = "资源不存在", detail: Optional[Any] = None) -> None:
        super().__init__(message, code=404, status_code=404, detail=detail)


class ConflictError(BankAIError):
    """资源冲突（如重复归档、重复创建）。"""

    def __init__(self, message: str = "资源冲突", detail: Optional[Any] = None) -> None:
        super().__init__(message, code=409, status_code=409, detail=detail)


# ---------------------------------------------------------------------------
# 外部系统与基础设施
# ---------------------------------------------------------------------------

class LLMError(BankAIError):
    """LLM 调用异常（RateLimit、Timeout、模型不可用等）。"""

    def __init__(self, message: str = "模型服务异常", detail: Optional[Any] = None) -> None:
        super().__init__(message, code=503, status_code=503, detail=detail)


class ParserError(BankAIError):
    """文档解析异常。"""

    def __init__(self, message: str = "文档解析失败", detail: Optional[Any] = None) -> None:
        super().__init__(message, code=422, status_code=422, detail=detail)


class DatabaseError(BankAIError):
    """数据库操作异常。"""

    def __init__(self, message: str = "数据库操作失败", detail: Optional[Any] = None) -> None:
        super().__init__(message, code=500, status_code=500, detail=detail)


# ---------------------------------------------------------------------------
# 文件与存储
# ---------------------------------------------------------------------------

class FileError(BankAIError):
    """文件操作异常（上传失败、格式不支持、保存失败）。"""

    def __init__(self, message: str = "文件处理失败", detail: Optional[Any] = None) -> None:
        super().__init__(message, code=400, status_code=400, detail=detail)
