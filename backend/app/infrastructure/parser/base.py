"""
app/infrastructure/parser/base.py
---------------------------------
文档解析抽象基类（Abstract Base Class）。

定义了解析层对上层暴露的统一契约（Contract）。
任何新增的具体解析引擎（如 Marker、MinerU、PDFPlumber 等）只需继承本类
并实现 parse_to_markdown_async 方法，即可无缝替换现有实现，而无需修改业务代码。
"""

from abc import ABC, abstractmethod


class BaseDocumentParser(ABC):
    """文档解析器抽象基类。

    所有具体解析适配器必须实现此接口，以保证上层业务（如合同比对、合同审查）
    对底层解析引擎的完全无感知。
    """

    @abstractmethod
    async def parse_to_markdown_async(self, file_path: str) -> str:
        """将本地文档文件异步解析为 Markdown 字符串。

        实现类内部必须将阻塞的 I/O 或 CPU 密集型视觉解析操作委托至线程池
       （例如通过 asyncio.to_thread），以避免阻塞主事件循环。

        Args:
            file_path: 本地文件的绝对或相对路径。

        Returns:
            解析后的 Markdown 格式字符串，需保留原始文档的层级标题、
            表格结构及段落顺序。

        Raises:
            FileNotFoundError: 当 file_path 指向的文件不存在时抛出。
            RuntimeError: 当解析引擎内部发生不可恢复错误时抛出。
        """
        ...
