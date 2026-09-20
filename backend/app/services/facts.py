"""设定事实清单（facts）与伏笔账本初始化。

把前置构建产物（角色、世界观规则/限制、伏笔）转成结构化事实行，
供 ConsistencyChecker 当作"设定事实清单"注入，实现按具体设定防"吃书"。
"""
from __future__ import annotations

from app.services.store import Story


def init_foreshadows(outline: list) -> list[dict]:
    """从卷章大纲中抽取伏笔（去空、去重），初始状态为 planted。"""
    fs: list[dict] = []
    seen: set[str] = set()
    for o in outline:
        raw = (o.get("foreshadow") or "").strip()
        if raw and raw not in seen:
            seen.add(raw)
            fs.append({
                "id": f"fs-{len(fs) + 1}",
                "text": raw,
                "origin": f"{o.get('type', '章节')} {o.get('no', '')}".strip(),
                "status": "planted",
            })
    return fs


def build_facts(story: Story) -> list[str]:
    """构建结构化设定事实清单（角色 / 世界规则与限制 / 已埋伏笔）。"""
    facts: list[str] = []
    for c in story.characters:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        role = "主角" if c.get("role") == "protagonist" else "配角"
        parts = [f"角色「{name}」({role})"]
        if c.get("goal"):
            parts.append(f"外在目标：{c['goal']}")
        if c.get("inner_need"):
            parts.append(f"内在需求：{c['inner_need']}")
        if c.get("flaw"):
            parts.append(f"缺点：{c['flaw']}")
        facts.append("；".join(parts))

    for rule in (story.world.get("rules") or []):
        facts.append(f"设定规则：{rule}")
    for con in (story.world.get("constraints") or []):
        facts.append(f"设定限制：{con}")

    for f in story.foreshadows:
        facts.append(f"已埋伏笔({f.get('status', 'planted')})：{f.get('text', '')}")

    return facts