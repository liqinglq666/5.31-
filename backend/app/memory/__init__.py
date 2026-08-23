"""
app/memory/
-----------
记忆层兼容层（Memory Layer Compatibility Shim）。

旧导入路径保持可用，新代码请使用 app.infrastructure.vectorstore
"""

from app.infrastructure.vectorstore.milvus import TopoMemoryManager

__all__ = ["TopoMemoryManager"]
