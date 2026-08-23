"""
services/web_search.py
----------------------
联网搜索服务：使用 DuckDuckGo 搜索，把结果注入 LLM 上下文。
无需 API Key，国内可用性一般，失败时静默降级。
"""

import logging
from typing import List

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5) -> List[dict]:
    """
    使用 DuckDuckGo 搜索，返回标题+摘要+链接列表。
    如果搜索失败，返回空列表（静默降级，不阻断主流程）。
    """
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)
            return [
                {
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "href": r.get("href", ""),
                }
                for r in results
            ]
    except Exception as exc:
        logger.warning("[WebSearch] DuckDuckGo 搜索失败: %s", exc)
        return []


def format_search_results(results: List[dict]) -> str:
    """把搜索结果格式化成文本，用于注入 prompt。"""
    if not results:
        return ""
    lines = ["【联网搜索结果】"]
    for idx, r in enumerate(results, 1):
        lines.append(f"{idx}. {r['title']}")
        lines.append(f"   摘要：{r['body']}")
        lines.append(f"   来源：{r['href']}")
        lines.append("")
    return "\n".join(lines)
