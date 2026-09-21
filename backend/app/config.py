"""应用配置：环境变量/密钥统一经 pydantic-settings 加载。

敏感信息（模型 API Key 等）只通过环境变量或 .env 传入，禁止写死入库。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Novel Gacha"
    version: str = "0.1.0"

    # 服务端机密：用于加密库中保存的模型 API Key（对称）。公网部署必须设置，
    # 且与模型 Key 分开保管；未设置时回退明文存储（仅限可信内网/本机）。
    secret_key: str = r""

    # 允许跨域的前端源（CORS）。公共部署下前后端同域（经反代），留空即为最严：
    # 不允许任何跨域请求（限同源）。仅在前端与 API 不同域时才需填写。
    cors_origins: list[str] = []

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

    # 简介生成的真实信息策略：默认在生成简介前就完成「知识库召回 + 网络预取」，
    # 把完整真实上下文作为前缀注入简介生成，让这本"全书种子"出生即带事实（而非凭模型记忆虚构）。
    # synopsis_recheck：对刚生成的简介再做一次事实校验门，检出臆断则回喂反馈重写一次。
    synopsis_grounded: bool = True
    synopsis_recheck: bool = True
    synopsis_max_retries: int = 2      # 简介重写上限（校验门在冲突时回喂重写的最大次数）

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

    # 章节 + 完结判定：生成正文后由轻量 LLM 判定"是否收束本章 / 是否走向结局"。
    chapters_enabled: bool = True                    # 关闭则退回“无限续写、不分章”的旧行为
    chapter_min_passages: int = 2                    # 提示 LLM 一章最少正文段数的软下界
    chapter_max_passages: int = 8                    # 提示 LLM 一章最多正文段数的软上界
    ending_max_chapters: int = 0                     # 硬性完结保险（0=关闭，纯 LLM 收敛判定）


settings = Settings()