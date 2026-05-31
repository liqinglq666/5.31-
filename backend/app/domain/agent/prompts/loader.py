"""
domain/agent/prompts/loader.py
------------------------------
Prompt 模板加载器。

- 使用 jinja2.Environment 加载 .jinja2 模板
- 通过 functools.lru_cache 缓存编译后的模板对象
- 支持变量插值（{{ variable }}）与模板片段复用（{% include %}）
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 模板文件所在目录
_PROMPTS_DIR = Path(__file__).parent

# 懒加载的 Jinja2 Environment 实例
_jinja_env: Optional[object] = None


def _get_env() -> object:
    """懒初始化 Jinja2 Environment。"""
    global _jinja_env
    if _jinja_env is None:
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError as exc:
            raise ImportError(
                "jinja2 未安装，无法加载 Prompt 模板。"
                "请执行 `pip install jinja2` 后重试。"
            ) from exc
        _jinja_env = Environment(
            loader=FileSystemLoader(str(_PROMPTS_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        logger.info("Jinja2 Environment 初始化完成，模板目录: %s", _PROMPTS_DIR)
    return _jinja_env


@lru_cache(maxsize=64)
def _get_template(name: str) -> object:
    """获取已编译的 Jinja2 Template（带缓存）。"""
    env = _get_env()
    template_path = f"{name}.jinja2"
    return env.get_template(template_path)


def load_prompt(name: str, **variables) -> str:
    """加载并渲染指定名称的 Prompt 模板。

    Args:
        name: 模板文件名（不含 .jinja2 后缀），如 "business" / "legal" / "supervisor"。
        **variables: 模板变量，用于 Jinja2 渲染。

    Returns:
        渲染后的纯文本字符串。

    Raises:
        ImportError: jinja2 未安装。
        RuntimeError: 模板文件不存在或渲染失败。
    """
    try:
        template = _get_template(name)
        rendered = template.render(**variables)
        return rendered
    except Exception as exc:
        logger.error("Prompt 模板加载失败 (%s): %s", name, exc)
        raise RuntimeError(f"Prompt 模板加载失败: {name}") from exc
