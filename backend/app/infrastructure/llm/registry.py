"""
core/model_config.py
--------------------
全局模型注册表（Registry Pattern）。
预置国内主流大模型配置，统一收敛 provider、base_url、env_key 等元数据。
新增模型只需在此字典中追加一行，零侵入业务代码。
"""

from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel


class ModelProvider(str, Enum):
    ZHIPU = "zhipu"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    MOONSHOT = "moonshot"
    DOUBAO = "doubao"
    MINIMAX = "minimax"
    OPENAI = "openai"


class ModelConfig(BaseModel):
    id: str
    name: str
    provider: ModelProvider
    version: str
    env_key: str
    base_url: str
    description: Optional[str] = None
    recommended: bool = False


# ---------------------------------------------------------------------------
# 模型注册表 —— 新增模型只需在此追加
# ---------------------------------------------------------------------------
MODEL_REGISTRY: Dict[str, ModelConfig] = {
    # 智谱 AI
    "glm-5-plus": ModelConfig(
        id="glm-5-plus",
        name="智谱 GLM-5 Plus",
        provider=ModelProvider.ZHIPU,
        version="5.0",
        env_key="zhipu_api_key",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        description="智谱旗舰模型，长上下文与复杂推理能力优异",
        recommended=True,
    ),
    "glm-5-flash": ModelConfig(
        id="glm-5-flash",
        name="智谱 GLM-5 Flash",
        provider=ModelProvider.ZHIPU,
        version="5.0",
        env_key="zhipu_api_key",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        description="智谱轻量高速模型，适合高并发场景",
    ),
    # DeepSeek
    "deepseek-chat": ModelConfig(
        id="deepseek-chat",
        name="DeepSeek V3",
        provider=ModelProvider.DEEPSEEK,
        version="3.0",
        env_key="deepseek_api_key",
        base_url="https://api.deepseek.com/v1",
        description="DeepSeek 通用对话模型，中文理解能力突出",
        recommended=True,
    ),
    "deepseek-reasoner": ModelConfig(
        id="deepseek-reasoner",
        name="DeepSeek R1",
        provider=ModelProvider.DEEPSEEK,
        version="3.0",
        env_key="deepseek_api_key",
        base_url="https://api.deepseek.com/v1",
        description="DeepSeek 推理模型，适合复杂逻辑分析与长文本",
    ),
    # 阿里通义千问
    "qwen-max": ModelConfig(
        id="qwen-max",
        name="通义千问 Max",
        provider=ModelProvider.QWEN,
        version="2.5",
        env_key="qwen_api_key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="阿里旗舰模型，金融法务场景优化",
        recommended=True,
    ),
    "qwen-plus": ModelConfig(
        id="qwen-plus",
        name="通义千问 Plus",
        provider=ModelProvider.QWEN,
        version="2.5",
        env_key="qwen_api_key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="阿里高性价比模型，均衡速度与精度",
    ),
    # 月之暗面 Kimi
    "moonshot-v1-8k": ModelConfig(
        id="moonshot-v1-8k",
        name="Kimi 8K",
        provider=ModelProvider.MOONSHOT,
        version="1.0",
        env_key="moonshot_api_key",
        base_url="https://api.moonshot.cn/v1",
        description="Moonshot 标准上下文模型",
    ),
    "moonshot-v1-32k": ModelConfig(
        id="moonshot-v1-32k",
        name="Kimi 32K",
        provider=ModelProvider.MOONSHOT,
        version="1.0",
        env_key="moonshot_api_key",
        base_url="https://api.moonshot.cn/v1",
        description="Moonshot 长上下文模型，适合长合同审查",
        recommended=True,
    ),
    # 字节豆包
    "doubao-pro-32k": ModelConfig(
        id="doubao-pro-32k",
        name="豆包 Pro 32K",
        provider=ModelProvider.DOUBAO,
        version="1.5",
        env_key="doubao_api_key",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        description="字节跳动企业级模型，推理稳定",
    ),
    "doubao-lite-32k": ModelConfig(
        id="doubao-lite-32k",
        name="豆包 Lite 32K",
        provider=ModelProvider.DOUBAO,
        version="1.5",
        env_key="doubao_api_key",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        description="字节跳动轻量模型，延迟极低",
    ),
    # MiniMax
    "abab6.5s-chat": ModelConfig(
        id="abab6.5s-chat",
        name="MiniMax 6.5s",
        provider=ModelProvider.MINIMAX,
        version="6.5",
        env_key="minimax_api_key",
        base_url="https://api.minimax.chat/v1",
        description="MiniMax 对话模型，多轮交互流畅",
    ),
    # OpenAI
    "gpt-4o": ModelConfig(
        id="gpt-4o",
        name="GPT-4o",
        provider=ModelProvider.OPENAI,
        version="4o",
        env_key="openai_api_key",
        base_url="https://api.openai.com/v1",
        description="OpenAI 旗舰多模态模型",
    ),
}


def get_model_config(model_id: str) -> ModelConfig:
    """根据模型 ID 获取配置，若不存在则抛异常。"""
    config = MODEL_REGISTRY.get(model_id)
    if not config:
        raise ValueError(f"Unknown model_id: {model_id}. Available: {list(MODEL_REGISTRY.keys())}")
    return config
