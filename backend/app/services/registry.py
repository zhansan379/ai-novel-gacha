"""单例组装：供路由层使用，避免重复构造。"""
from __future__ import annotations

from app.config import settings
from app.llm import LLMGateway
from app.services.direction import DirectionGenerator
from app.services.grounding import make_grounding
from app.services.keychain import Keychain
from app.services.story_service import StoryService
from app.services.store import StoryStore
from app.services.writer import WriterAgent
from app.storage.sqlite import SQLiteStore

store: StoryStore = SQLiteStore(settings.db_path)  # SQLite 持久化（写透 + 缓存）
keychain = Keychain(settings.db_path)              # 运行时模型接入配置（前端可设）
gateway = LLMGateway(settings, keychain=keychain)
_direction = DirectionGenerator(gateway)
_writer = WriterAgent(gateway)
_grounding = make_grounding(settings, gateway=gateway)
story_service = StoryService(store, gateway, _direction, _writer, grounding=_grounding)