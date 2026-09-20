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

    # 真实世界事实基座：网络搜索（可选增强，二阶段）。未配置搜索密钥 → 仅用内置知识库。
    # 内置知识库：backend/data/knowledge_base.json
    search_provider: str = "tavily"
    search_api_key: str = ""
    search_timeout: float = 15.0

    # 检索画像（retrieval profile）：开书时一次 LLM 判定本书按"真实事实/专业/时效/设定连续性"
    # 四维度需要什么，产出中文专题清单供网络预取。判定失败回退关键词兜底，绝不阻塞开书。
    profiling_enabled: bool = True
    profiling_max_topics: int = 4      # 开书最大并行预取专题数（受并发闸门节制）

    # Chroma 内置真实知识库（唯一事实来源）
    chroma_path: str = "data/chroma"
    embedding_mode: str = "n-gram"   # "n-gram"(默认,离线) | "llm"(外部 /embeddings, 语义更强)
    embedding_model: str = ""        # llm 模式下的 embedding 模型名；留空则回落 n-gram
    embed_timeout: float = 20.0

    # 持久化（SQLite）
    db_path: str = "data/app.db"

    # 异步开书任务：并发闸门 + 循环队列清扫（页面刷新安全；服务重启会丢未完成任务）
    task_concurrency: int = 4        # 全局同时运行的开书任务/内部扇出上限（保护厂商限流）
    task_ttl_seconds: int = 3600     # 已完成/出错任务保活秒数，到期清扫释放内存
    task_max_retained: int = 200     # 最多保留的任务条数，超出优先淘汰最旧的
    # 单书内部扇出：按依赖 DAG 分波并行（自动文风∥检索∥骨架；再并行世界观/历史/角色/伏笔；卡池∥开篇）。
    # 关闭则退回旧的单调用串联（约省 4 路 LLM 调用，慢但省 token）。
    book_fanout: bool = True


settings = Settings()