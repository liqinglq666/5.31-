"""
spatial_indexer.py
------------------
V3.1 视觉溯源旁路增强方案 —— 空间索引引擎。

职责：在主干 Docling 解析的同时，旁路并行扫描 PDF 全文，
提取每个文本块的物理坐标（bbox）、页码（page_index）和归一化文本（norm_text），
供终点钩子将 AI 发现的风险文本绑定到 PDF 像素位置。

设计约束：
- 零 LLM 调用，纯 Python + PyMuPDF（fitz）计算。
- 同步 CPU 密集型，必须由调用方用 asyncio.to_thread() 包裹。
- fitz 是 C/C++ 底层绑定，必须用 with 语句管理内存生命周期。
"""

import logging
import re
from typing import Optional

import fitz  # PyMuPDF

from app.domain.models.visual_evidence import SpatialBlock, SpatialIndex

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 文本归一化（与 contract_review.py 中 _pre_validate_differences 保持一致）
# ---------------------------------------------------------------------------

_CJK_RADICAL_MAP = str.maketrans("⽇⽉⾄⽌⼄⽅⽬", "日月至止乙方目")


def _normalize(text: str) -> str:
    """归一化：剔除 Markdown 排版、换行、空格、全半角差异，用于模糊匹配。"""
    if not text:
        return ""
    # 1. CJK 部首字符还原（OCR 误识别）
    text = text.translate(_CJK_RADICAL_MAP)
    # 2. 剔除所有空白字符
    text = re.sub(r"\s+", "", text)
    # 3. 剔除常见标点 + Markdown 格式符（Pipe Artifact 防护）
    text = re.sub(r"[，。；：！？\"'（）【】\[\]、\|\*]", "", text)
    return text.lower()


# ---------------------------------------------------------------------------
# 空间索引构建
# ---------------------------------------------------------------------------

def build_spatial_index(task_id: str, pdf_path: str) -> SpatialIndex:
    """同步构建单份 PDF 的空间坐标索引。

    注意：此函数为纯同步 CPU 密集型操作，外层必须用 asyncio.to_thread() 包裹，
    禁止直接 await 或 asyncio.create_task() 裸调，否则将阻塞 Asyncio 事件循环。

    物理坑防护：
    - 纯图扫描件（无内嵌文本层）：get_text("dict") 返回空列表，索引为空，
      前端通过 visual_evidence 为 null 做优雅降级。
    - C 层内存泄漏：通过 with 语句确保 fitz.Document 即时释放。
    """
    blocks = []
    try:
        with fitz.open(pdf_path) as doc:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text_dict = page.get_text("dict")
                for b in text_dict.get("blocks", []):
                    # 只取文本块（type == 0），跳过图片/图形
                    if b.get("type") != 0:
                        continue
                    text = "".join(
                        span["text"]
                        for line in b.get("lines", [])
                        for span in line.get("spans", [])
                    )
                    norm = _normalize(text)
                    if norm:
                        blocks.append(
                            SpatialBlock(
                                page_index=page_num,
                                bbox=tuple(b["bbox"]),  # [x0, y0, x1, y1]
                                norm_text=norm,
                            )
                        )
    except Exception as exc:
        logger.warning(
            "[SpatialIndexer] 构建空间索引失败 task_id=%s path=%s: %s",
            task_id, pdf_path, exc,
        )
        # 失败返回空索引，主干不受影响

    logger.info(
        "[SpatialIndexer] 索引构建完成 task_id=%s blocks=%d path=%s",
        task_id, len(blocks), pdf_path,
    )
    return SpatialIndex(task_id=task_id, blocks=blocks)
