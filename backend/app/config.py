"""应用配置：环境变量/密钥统一经 pydantic-settings 加载。

敏感信息（模型 API Key 等）只通过环境变量或 .env 传入，禁止写死入库。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Novel Gacha"
    version: str = "0.1.0"

    # 模型接入（BYOK）：由用户自行配置，走 OpenAI 兼容协议
    default_provider: str = "deepseek"
    default_model: str = "deepseek-chat"
    # 示例：{"deepseek": "sk-...", "openai": "sk-..."}
    api_keys: dict[str, str] = {}
    # 各厂商 OpenAI 兼容 Base URL；缺省回退 openai_compat_base_url
    base_urls: dict[str, str] = {}
    openai_compat_base_url: str = "https://api.deepseek.com/v1"
    llm_timeout: float = 60.0

    # 持久化（SQLite）
    db_path: str = "data/app.db"


settings = Settings()