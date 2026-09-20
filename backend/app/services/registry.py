"""单例组装：供路由层使用，避免重复构造。"""
from __future__ import annotations

from app.config import settings
from app.llm import LLMGateway
from app.services.direction import DirectionGenerator
from app.services.story_service import StoryService
from app.services.store import StoryStore
from app.services.writer import WriterAgent

store = StoryStore()
gateway = LLMGateway(settings)
_direction = DirectionGenerator(gateway)
_writer = WriterAgent(gateway)
story_service = StoryService(store, gateway, _direction, _writer)