"""单例组装：供路由层使用，避免重复构造。"""
from __future__ import annotations

from app.config import settings
from app.context import current_user_id
from app.llm import LLMGateway
from app.services.auth import AuthManager
from app.services.direction import DirectionGenerator
from app.services.grounding import make_grounding
from app.services.keychain import Keychain
from app.services.progression import ProgressionService
from app.services.retrieval import ProfileDeterminer
from app.services.story_service import StoryService
from app.services.store import StoryStore
from app.services.tasks import TaskManager
from app.services.writer import WriterAgent
from app.storage.sqlite import SQLiteStore

store: StoryStore = SQLiteStore(settings.db_path)    # SQLite 持久化（写透 + 缓存）
auth = AuthManager(settings.db_path)                 # 用户注册/登录/会话
keychain = Keychain(settings.db_path, secret_key=settings.secret_key)  # 每用户模型接入（Key 加密落地）
gateway = LLMGateway(settings, keychain=keychain)
_direction = DirectionGenerator(gateway)
_writer = WriterAgent(gateway)
_grounding = make_grounding(settings, gateway=gateway)
_profiler = ProfileDeterminer(gateway)
_progression = ProgressionService(gateway)
story_service = StoryService(store, gateway, _direction, _writer, grounding=_grounding,
                             profiler=_profiler, progression=_progression)
tasks = TaskManager()                              # 异步开书任务注册表（后台执行 + 轮询状态）