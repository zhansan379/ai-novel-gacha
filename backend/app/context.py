"""每请求当前用户上下文。

用 ContextVar 承载"当前登录用户"，由路由层的鉴权依赖在进入时设置。
FFI 层（gateway.resolve / 归属校验）只用读取它，即可拿到自己的 keychain 与数据，
无需把 user_id 显式穿透整个服务层。后台任务（asyncio.create_task）会自动继承
设置时的上下文，因此异步开书任务也能识别归属。
"""
from __future__ import annotations

from contextvars import ContextVar

current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)