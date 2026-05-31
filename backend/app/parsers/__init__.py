"""
app/parsers/
-----------
文档解析层兼容层（Parser Layer Compatibility Shim）。

旧导入路径保持可用，新代码请使用 app.infrastructure.parser
"""

from app.infrastructure.parser.base import BaseDocumentParser
from app.infrastructure.parser.docling import DoclingParserAdapter

__all__ = [
    "BaseDocumentParser",
    "DoclingParserAdapter",
]
