"""
domain/agent/prompts/
---------------------
Prompt 模板目录。

所有 System Prompt 均以 Jinja2 模板形式存放，支持变量插值与版本控制。
加载器提供编译缓存，避免运行时重复解析模板语法。
"""

from app.domain.agent.prompts.loader import load_prompt

__all__ = ["load_prompt"]
