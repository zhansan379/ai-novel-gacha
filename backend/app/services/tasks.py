"""异步开书任务注册表：提交即返回 task_id，后台 asyncio 任务跑完 StoryService.create，
供前端定时轮询真实进度；全局信号量限流，兼顾多本书并行与单书内部扇出。

- 页面刷新安全：任务留在进程内存中，服务端不因客户端断连而中断。
- 服务重启会丢未完成任务（已完成的书已落 SQLite，不受影响；前端轮询 404 便知晓）。
- asyncio.Semaphore(task_concurrency) 是全局闸门：无论跨书并发还是单书内部扇出的
  并行调用，都受它节制，避免打爆模型厂商限流。
- 已完成/出错任务按 TTL 与条数上限清扫，防止内存无限增长。

与 registry 解耦：submit 接收一个「job 协程工厂」（由路由层用 registry.story_service
构造并注入 on_stage 回调），tasks 自身不 import registry，避免循环引用。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from enum import Enum
from typing import Any, Awaitable, Callable

from app.config import settings
from app.llm.errors import LLMError, QuotaError


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class CreateTask:
    __slots__ = ("task_id", "premise", "status", "stage", "created_at",
                 "started_at", "finished_at", "result", "error")

    def __init__(self, task_id: str, premise: str = "") -> None:
        self.task_id = task_id
        self.premise = premise
        self.status = TaskStatus.PENDING
        self.stage = "已提交，排队中"
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.result: dict | None = None
        self.error: dict | None = None


def _story_result(story) -> dict:
    """把 create 返回的 Story 压成与 StoryCreated 一致的外部形态（供轮询返回值）。"""
    d = story.decisions.get(getattr(story, "next_decision_no", 1))
    cards = [c.model_dump() for c in d.cards] if d and d.cards else []
    opening = story.passages[0]["content"] if story.passages else ""
    return {
        "story_id": story.id,
        "synopsis": story.synopsis,
        "opening": opening,
        "decision_no": getattr(story, "next_decision_no", 1),
        "cards": cards,
        "style_profile_id": story.style_profile_id,
    }


def _classify(exc: BaseException) -> dict:
    if isinstance(exc, QuotaError):
        return {"code": "QUOTA_EXCEEDED", "message": str(exc)}
    if isinstance(exc, LLMError):
        return {"code": "MODEL_ERROR", "message": str(exc)}
    return {"code": "TASK_FAILED", "message": str(exc)}


class TaskManager:
    def __init__(self, *, concurrency: int | None = None, ttl: int | None = None,
                 max_retained: int | None = None) -> None:
        self._tasks: dict[str, CreateTask] = {}
        self._sem = asyncio.Semaphore(concurrency if concurrency is not None else settings.task_concurrency)
        self._ttl = ttl if ttl is not None else settings.task_ttl_seconds
        self._max = max_retained if max_retained is not None else settings.task_max_retained

    def submit(self, job: Callable[[Callable[[str], None]], Awaitable], premise: str = "") -> str:
        """登记一个开书任务并后台执行，立即返回 task_id。

        job: async (on_stage: Callable[[str], None]) -> Story，由调用方注入 on_stage 上报阶段。
        """
        task_id = uuid.uuid4().hex
        self._tasks[task_id] = CreateTask(task_id, premise)
        asyncio.get_running_loop().create_task(self._run(task_id, job))
        self._sweep()
        return task_id

    async def _run(self, task_id: str,
                   job: Callable[[Callable[[str], None]], Awaitable]) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        async with self._sem:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()

            def on_stage(stage: str) -> None:
                rec = self._tasks.get(task_id)
                if rec is not None:
                    rec.stage = stage

            try:
                story: Any = await job(on_stage)
                rec = self._tasks.get(task_id)
                if rec is None:
                    return
                rec.status = TaskStatus.DONE
                rec.result = _story_result(story)
            except Exception as exc:  # 失败不阻断其他任务
                rec = self._tasks.get(task_id)
                if rec is None:
                    return
                rec.status = TaskStatus.ERROR
                rec.error = _classify(exc)
            finally:
                rec = self._tasks.get(task_id)
                if rec is not None:
                    rec.finished_at = time.time()

    def get(self, task_id: str) -> CreateTask | None:
        self._sweep()
        return self._tasks.get(task_id)

    def reset(self) -> None:
        """清空任务表（测试隔离用）。"""
        self._tasks.clear()

    def _sweep(self) -> None:
        now = time.time()
        for tid in [t for t, tk in self._tasks.items()
                    if tk.finished_at and (now - tk.finished_at) > self._ttl]:
            del self._tasks[tid]
        if len(self._tasks) > self._max:
            finished = sorted(
                (t for t, tk in self._tasks.items() if tk.finished_at),
                key=lambda t: self._tasks[t].finished_at or 0,
            )
            for tid in finished[: len(self._tasks) - self._max]:
                del self._tasks[tid]