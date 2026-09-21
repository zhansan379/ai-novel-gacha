"""按任务定义模型调用参数（温度 / 最大 token）。

设计参考 AI-Novel-Writing-Assistant：「前置设定」更稳、「正文」更有文采、「校验」最稳。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    temperature: float
    max_tokens: int


ROUTES: dict[str, Route] = {
    # 简介生成：鼓励跳出网文模板，偏高温度求新颖（文风选择等稳定的 init 任务仍走「init」）
    "synopsis": Route(temperature=0.9, max_tokens=600),
    # 卡池/世界观/历史/大纲等前置设定：稳定
    "init": Route(temperature=0.5, max_tokens=600),
    "blueprint": Route(temperature=0.5, max_tokens=1500),
    "direction": Route(temperature=0.7, max_tokens=1200),
    # 正文：更有文采（每拍 700~1000 字，需足够 token 避免截断）
    "draft": Route(temperature=0.8, max_tokens=4000),
    # 一致性/审稿：最稳
    "consistency": Route(temperature=0.0, max_tokens=600),
    # 叙事状态更新（伏笔推进/角色/关系递增）：紧凑、偏执信
    "narrative_update": Route(temperature=0.2, max_tokens=450),
}

DEFAULT_ROUTE = Route(temperature=0.7, max_tokens=800)


def route_for(task: str) -> Route:
    return ROUTES.get(task, DEFAULT_ROUTE)