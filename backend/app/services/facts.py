"""设定事实清单（facts）与伏笔账本初始化。

把前置构建产物（角色、世界观规则/限制、伏笔）转成结构化事实行，
供 ConsistencyChecker 当作"设定事实清单"注入，实现按具体设定防"吃书"。
"""
from __future__ import annotations

from app.services.grounding import GROUNDING_LABEL
from app.services.store import Story


def init_foreshadows(seeds: list) -> list[dict]:
    """从蓝图伏笔种子抽取初始伏笔（去空、去重），初始状态为 planted。"""
    fs: list[dict] = []
    seen: set[str] = set()
    for seed in seeds:
        # 兼容旧 outline 结构（{foreshadow: ...}），新格式为纯字符串种子
        raw = (seed.get("foreshadow") or "").strip() if isinstance(seed, dict) else str(seed).strip()
        if raw and raw not in seen:
            seen.add(raw)
            fs.append({
                "id": f"fs-{len(fs) + 1}",
                "text": raw,
                "origin": "初始设定",
                "status": "planted",
            })
    return fs


def build_narrative_context(story: Story) -> str:
    """当前叙事状态摘要：世界约束 + 角色现状 + 伏笔账本。

    注入正文/卡池生成的 prompt，让"当前角色与伏笔"真正参与剧情走向；
    区别于 build_facts（那份是给质检的强制清单）。
    """
    lines: list[str] = []
    for rule in (story.world.get("rules") or []):
        lines.append(f"- 世界规则：{rule}")
    for con in (story.world.get("constraints") or []):
        lines.append(f"- 世界限制：{con}")
    for c in story.characters:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        role = "主角" if c.get("role") == "protagonist" else "配角"
        part = f"- 角色「{name}」({role})"
        if c.get("goal"):
            part += f"：目标 {c['goal']}"
        if c.get("trait"):
            part += f"，特征 {c['trait']}"
        if c.get("moves"):
            part += f"；本段动向：{'、'.join(c['moves'])}"
        lines.append(part)
    status_txt = {"planted": "已埋", "advanced": "推进中", "paid_off": "已兑现"}
    for f in story.foreshadows:
        st = status_txt.get(f.get("status"), f.get("status"))
        lines.append(f"- 伏笔({st})：{f.get('text', '')}")
    if story.grounding:
        lines.append(GROUNDING_LABEL)
        lines.extend(f"- {line.lstrip('• ')}" for line in story.grounding)
    for r in story.relations:
        a, b, label = r.get("a"), r.get("b"), r.get("label") or ""
        if a and b:
            lines.append(f"- 关系：{a} {label or '与'} {b}（{r.get('note') or ''}）")
    return "\n".join(lines)


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

    for line in story.grounding:
        facts.append(f"真实事实：{line.lstrip('• ')}")

    for r in story.relations:
        a, b, label = r.get("a"), r.get("b"), r.get("label") or ""
        if a and b:
            facts.append(f"设定关系：{a} {label or '与'} {b}（{r.get('note') or ''}）")

    return facts