from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_url: str = "postgresql://postgres:123456@localhost:5432/bank-ai"
    redis_url: str = "redis://localhost:6379/0"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.moonshot.cn/v1"
    llm_model: str = "kimi-k2.6"
    llm_embedding_model: str = "moonshot-v1-embedding"

    # 大模型动态配置加密盐（仅用于加密/解密 sys_model_configs 表中的 API Key）
    db_encryption_key: str = ""

    # 多模型 API Keys（Registry Pattern 兼容层 —— 数据库无配置时的 fallback）
    # 建议迁移完成后逐步废弃，统一走 sys_model_configs 管理
    zhipu_api_key: str = ""
    deepseek_api_key: str = ""
    qwen_api_key: str = ""
    moonshot_api_key: str = ""
    doubao_api_key: str = ""
    minimax_api_key: str = ""
    openai_api_key: str = ""
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"

    # Milvus 向量数据库配置
    milvus_host: str = "localhost"
    milvus_port: str = "19530"
    milvus_collection: str = "contract_chunks"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    # 本地模型路径（优先于在线下载，为空则走 HuggingFace）
    embedding_model_local_path: str = ""

    api_limit: int = 10
    secret_key: str = "super-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_hours: int = 24

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
