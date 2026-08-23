"""
app/infrastructure/parser/docling.py
------------------------------------
Docling 高保真文档解析适配器（Concrete Adapter）。

封装 IBM Docling 的视觉解析能力：
- DocLayNet：用于版面分析（Layout Analysis），识别标题、段落、表格区域。
- TableFormer：用于表格结构重建，输出标准 Markdown 表格语法。

所有同步阻塞调用均已通过 asyncio.to_thread 异步化，可直接在 FastAPI 的
异步上下文中安全使用。
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

# 关键：强制 Docling 从本地缓存加载模型，避免容器内 huggingface_hub 因网络
# 验证失败而反复尝试下载。模型由 download_models() 预先下载到该目录。
_DOCLING_MODEL_CACHE = Path("/root/.cache/docling/models")
if _DOCLING_MODEL_CACHE.exists():
    try:
        from docling.datamodel.settings import settings

        settings.artifacts_path = _DOCLING_MODEL_CACHE
        logging.getLogger(__name__).info(
            "Docling artifacts_path 已指向本地缓存: %s", _DOCLING_MODEL_CACHE
        )
    except Exception:
        pass

from app.infrastructure.parser.base import BaseDocumentParser

logger = logging.getLogger(__name__)

# 线程局部存储：每个工作线程拥有独立的 DocumentConverter 实例，
# 彻底规避 ONNX Runtime / PyTorch 在多线程并发推理时的 Segfault 风险。
_thread_local = threading.local()


def _get_thread_local_converter() -> object:
    """懒加载并缓存当前线程绑定的 DocumentConverter 实例。

    首次调用时动态导入 docling，避免在 docling 未安装的环境中
    触发 ImportError（此时上层可优雅回退到其他解析器）。

    Returns:
        已初始化的 DocumentConverter 实例（线程隔离）。

    Raises:
        ImportError: 当 docling 包未安装时抛出，附带安装指引。
    """
    if not hasattr(_thread_local, "converter"):
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as exc:
            raise ImportError(
                "docling 未安装，无法启用视觉解析。"
                "请执行 `pip install docling` 后重试。"
            ) from exc

        _thread_local.converter = DocumentConverter()
        logger.info(
            "Docling DocumentConverter 初始化完成（线程 %s）",
            threading.current_thread().name,
        )

    return _thread_local.converter


class DoclingParserAdapter(BaseDocumentParser):
    """基于 IBM Docling 的高保真文档解析适配器。

    专为含复杂表格与多栏版式的金融合同 PDF 优化。
    通过线程局部存储（Thread-Local Storage）管理 DocumentConverter 生命周期，
    每个工作线程持有独立模型副本，既消除重复初始化开销，又规避多线程并发崩溃风险。
    """

    # ------------------------------------------------------------------
    # 同步解析内核（私有，禁止直接调用，防止阻塞事件循环）
    # ------------------------------------------------------------------

    def _parse_to_markdown_sync(self, file_path: str) -> str:
        """同步内核：将本地 PDF 文件解析为高保真 Markdown。

        合同中的复杂表格将以标准 Markdown 表格语法输出，行列对齐由
        docling 的 TableFormer 保证，避免传统正则方案常见的错配问题。

        Args:
            file_path: 本地 PDF 文件路径。

        Returns:
            解析后的 Markdown 字符串。

        Raises:
            FileNotFoundError: 文件不存在。
            RuntimeError: docling 解析过程中发生异常。
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        converter = _get_thread_local_converter()
        logger.info("开始解析文件: %s", path.name)

        try:
            result = converter.convert(str(path))
            markdown: str = result.document.export_to_markdown()
            logger.info(
                "解析完成: %s，共 %d 字符，标题层级 %d",
                path.name,
                len(markdown),
                markdown.count("#"),
            )
            return markdown
        except Exception as exc:
            logger.error(
                "Docling 解析失败 (%s): %s",
                path.name,
                exc,
                exc_info=True,
            )
            raise RuntimeError(f"文档解析失败: {exc}") from exc

    def _parse_from_bytes_sync(self, file_bytes: bytes, suffix: str = ".pdf") -> str:
        """同步内核：将内存中的文件字节流通过临时文件交给 docling 解析。

        适用于 FastAPI UploadFile 等已经将文件读取为 bytes 的场景。
        临时文件会在解析完成后自动清理。

        Args:
            file_bytes: 文件二进制内容。
            suffix: 临时文件后缀，用于帮助 docling 识别文档格式。

        Returns:
            解析后的 Markdown 字符串。
        """
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as tmp_file:
                tmp_file.write(file_bytes)
            return self._parse_to_markdown_sync(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # 异步公共接口（实现 BaseDocumentParser 契约）
    # ------------------------------------------------------------------

    async def parse_to_markdown_async(self, file_path: str) -> str:
        """异步接口实现：解析本地文件。

        将阻塞的视觉模型推理委托至默认线程池，确保 FastAPI 事件循环不被阻塞。

        Args:
            file_path: 本地 PDF 文件路径。

        Returns:
            解析后的 Markdown 字符串。
        """
        return await asyncio.to_thread(self._parse_to_markdown_sync, file_path)

    # ------------------------------------------------------------------
    # 扩展异步接口（非基类强制，但业务层高频使用）
    # ------------------------------------------------------------------

    async def parse_from_bytes_async(
        self,
        file_bytes: bytes,
        suffix: str = ".pdf",
    ) -> str:
        """扩展异步接口：支持内存字节流解析。

        Args:
            file_bytes: 文件二进制内容。
            suffix: 临时文件后缀。

        Returns:
            解析后的 Markdown 字符串。
        """
        return await asyncio.to_thread(
            self._parse_from_bytes_sync, file_bytes, suffix
        )
