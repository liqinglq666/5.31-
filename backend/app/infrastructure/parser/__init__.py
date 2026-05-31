"""
app/infrastructure/parser/
--------------------------
文档解析层基础设施（Adapter Pattern）。

通过抽象基类 BaseDocumentParser 将底层解析引擎与上层业务完全解耦。
当前提供 DoclingParserAdapter 作为高保真视觉解析的具体实现。
"""

from app.infrastructure.parser.base import BaseDocumentParser
from app.infrastructure.parser.docling import DoclingParserAdapter

__all__ = [
    "BaseDocumentParser",
    "DoclingParserAdapter",
]
