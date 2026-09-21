"""设定事实清单（facts）与伏笔账本初始化。

把前置构建产物（角色、世界观规则/限制、伏笔）转成结构化事实行，
供 ConsistencyChecker 当作"设定事实清单"注入，实现按具体设定防"吃书"。

build_narrative_context 是"给生成 prompt 的当前叙事状态摘要"：有界注入 + 相关裁剪——
恒保留世界规则/限制、主角、真实事实基座；据最近一拍的剧情（story.timeline）召回近期前文，
并对超限的角色/伏笔/关系做相关度裁剪，避免长书全量注入越写越臃肿。
build_facts 则是"给质检的完整约束清单"，始终返回全部设定，不受裁剪影响。
"""
from __future__ import annotations

import re

from app.services.grounding import GROUNDING_LABEL
from app.services.store import Story, normalize_factions


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


def _normalize(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _bigrams(s: str) -> set[str]:
    """去除空白后的相邻二元组，用作中文文本的相关度判据（确定性、局域）。"""
    t = _normalize(s)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _overlap_count(a: str, b: str) -> int:
    return len(_bigrams(a) & _bigrams(b))


def _relevance_key(story: Story) -> str:
    """相关键 = 最近一拍（摘要/标题/标签/模式）。timeline 空时为空串，不裁剪任何设定。"""
    if not story.timeline:
        return ""
    last = story.timeline[-1]
    return " ".join(str(last.get(k) or "") for k in ("summary", "title", "label", "mode"))


def _recent_memory(story: Story, max_recent: int) -> str:
    """近期剧情（前文召回）：最后 max_recent 拍的摘要块，有界。开篇（timeline 空）为空。"""
    if not story.timeline:
        return ""
    lines = []
    for t in story.timeline[-max_recent:]:
        no = t.get("no")
        title = (t.get("title") or "").strip()
        mode = t.get("mode") or ""
        summary = (t.get("summary") or "").strip()
        if no and title:
            head = f"#{no} {title}"
        elif no:
            head = f"#{no} [{mode}]"
        elif title:
            head = title
        else:
            head = f"[{mode}]"
        lines.append(f"- {head}：{summary}" if summary else f"- {head}")
    return "【近期剧情】\n" + "\n".join(lines)


def _clip_characters(characters: list, key: str, max_chars: int) -> list:
    """角色裁剪：≤max_chars 全量；超限保留主角 + 按"名/目标/特征与近拍相关度"取高者。"""
    chars = [c for c in characters if (c.get("name") or "").strip()]
    if len(chars) <= max_chars:
        return chars
    prot = [c for c in chars if c.get("role") == "protagonist"]
    others = [c for c in chars if c.get("role") != "protagonist"]
    scored = sorted(
        others,
        key=lambda c: (-_overlap_count(" ".join(str(c.get(k) or "") for k in ("name", "goal", "trait")), key),
                       c.get("name") or ""),
    )
    return prot + scored[: max(0, max_chars - len(prot))]


def _clip_foreshadows(foreshadows: list, key: str, max_foreshadows: int) -> list:
    """伏笔裁剪：≤max 全量；超限优先未兑现、其次与近拍相关、再次较新。"""
    fs = list(foreshadows)
    if len(fs) <= max_foreshadows:
        return fs
    ranked = sorted(
        enumerate(fs),
        key=lambda it: (it[1].get("status") == "paid_off",
                        -_overlap_count(str(it[1].get("text") or ""), key),
                        -it[0]),
    )
    return [f for _, f in ranked[:max_foreshadows]]


def _clip_relations(relations: list, keep_names: set, max_relations: int) -> list:
    """关系裁剪：≤max 全量；超限优先两端命中已保留角色的边，保持相对拓扑。"""
    if len(relations) <= max_relations:
        return relations

    def hits(r) -> int:
        return (1 if r.get("a") in keep_names else 0) + (1 if r.get("b") in keep_names else 0)

    return sorted(relations, key=hits, reverse=True)[:max_relations]


def build_narrative_context(story: Story, *, max_recent: int = 4,
                            max_chars: int = 6, max_foreshadows: int = 8,
                            max_relations: int = 10) -> str:
    """当前叙事状态摘要：近期剧情 + 世界约束 + 相关角色/伏笔 + 关系账本 + 真实事实。

    注入正文/卡池生成的 prompt，让"当前角色与伏笔"真正参与剧情走向；
    区别于 build_facts（那份是给质检的强制清单，始终完整）。
    默认参数保守：多数书（角色≤6、伏笔≤8、关系≤10）不裁剪，仅新增近期剧情块。
    """
    key = _relevance_key(story)
    lines: list[str] = []
    recent = _recent_memory(story, max_recent)
    if recent:
        lines.append(recent)
    for rule in (story.world.get("rules") or []):
        lines.append(f"- 世界规则：{rule}")
    for con in (story.world.get("constraints") or []):
        lines.append(f"- 世界限制：{con}")
    for f in normalize_factions(story.world.get("factions")):
        lines.append(f"- 势力「{f['name']}」：{f['description']}" if f["description"] else f"- 势力「{f['name']}」")
    for c in _clip_characters(story.characters, key, max_chars):
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
    for f in _clip_foreshadows(story.foreshadows, key, max_foreshadows):
        st = status_txt.get(f.get("status"), f.get("status"))
        lines.append(f"- 伏笔({st})：{f.get('text', '')}")
    # 真实事实放在角色/伏笔之后、世界约束内即合理；label 已声明"高于简介"，一并注入。
    if story.grounding:
        lines.append(GROUNDING_LABEL)
        lines.extend(f"- {line.lstrip('• ')}" for line in story.grounding)
    keep_names = {c["name"] for c in _clip_characters(story.characters, key, max_chars) if c.get("name")}
    for r in _clip_relations(story.relations, keep_names, max_relations):
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
    for f in normalize_factions(story.world.get("factions")):
        facts.append(f"势力：{f['name']}——{f['description']}" if f["description"] else f"势力：{f['name']}")

    for f in story.foreshadows:
        facts.append(f"已埋伏笔({f.get('status', 'planted')})：{f.get('text', '')}")

    for line in story.grounding:
        facts.append(f"真实事实：{line.lstrip('• ')}")

    for r in story.relations:
        a, b, label = r.get("a"), r.get("b"), r.get("label") or ""
        if a and b:
            facts.append(f"设定关系：{a} {label or '与'} {b}（{r.get('note') or ''}）")

    return facts