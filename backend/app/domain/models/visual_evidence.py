"""
Visual Evidence —— PDF 空间坐标定位数据模型。
为 V3.1 视觉溯源旁路增强方案提供数据结构支持。
"""

from typing import Optional, List
from pydantic import BaseModel


class VisualEvidence(BaseModel):
    """单条风险差异在 PDF 原文中的空间坐标证据。"""

    page_index: int                          # 0-based 页码
    bbox: tuple[float, float, float, float]  # [x0, y0, x1, y1]，PDF 物理点数（Points）
    matched_text: str                        # 归一化后匹配到的文本片段
    confidence: float = 1.0                  # 匹配置信度 0~1


class SpatialBlock(BaseModel):
    """PyMuPDF 提取的单个文本块，用于构建空间索引。"""

    page_index: int
    bbox: tuple[float, float, float, float]
    norm_text: str                           # 归一化后的文本（去空白/去标点/CJK 还原）


class SpatialIndex(BaseModel):
    """单份（或多份）PDF 的空间坐标索引。"""

    task_id: str
    blocks: List[SpatialBlock]

    def fuzzy_match(self, norm_text: str) -> Optional[SpatialBlock]:
        """用归一化文本在索引中做弹性匹配。

        先尝试完整包含匹配，失败则尝试子串匹配。
        返回首个命中的 SpatialBlock。
        """
        if not norm_text:
            return None

        # 1. 完整包含匹配（优先）
        for block in self.blocks:
            if norm_text in block.norm_text:
                return block

        # 2. 子串匹配（block 文本较短，被 norm_text 包含）
        for block in self.blocks:
            if block.norm_text in norm_text and len(block.norm_text) >= 8:
                return block

        return None
