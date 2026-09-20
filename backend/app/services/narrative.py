"""叙事状态更新（NarrativeUpdater）：每次决策正文生成后推进伏笔 / 增量更新角色 / 关系。

- 把"当前角色 + 伏笔账本 + 关系账本 + 新写正文"交给 LLM，产出紧凑 JSON 状态更新。
- 伏笔推进/回收（planted → advanced → paid_off）、可新埋；角色可增量改或新登场。
- advance_plan 做差分门控：按剧情浓度决定本次推进哪些账本（低浓度过场只推进关系，
  不惊动伏笔），并把"是否启用某账本"传进 update 的提示词与落账逻辑。
- 宽容处理：解析失败或上游异常时原样返回旧状态，绝不因为这次辅助更新影响正文生成。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.llm import LLMGateway
from app.schemas import DirectionKind
from app.services.jsonparse import loads_coerce

_FORESHADOW_STATUSES = {"planted", "advanced", "paid_off"}

# 高浓度档：全面推进三账本；低浓度档（SCENE 过场）只推关系，不惊动伏笔/不凭空改角色
_HIGH_CONCENTRATION_KINDS = {
    DirectionKind.EVENT, DirectionKind.ACTION, DirectionKind.MEETING,
    DirectionKind.FORESHADOW, DirectionKind.CUSTOM,
}


def _narrative_system(*, advance_characters: bool, advance_foreshadows: bool,
                      advance_relations: bool) -> str:
    """按本次启用的账本动态拼系统提示词，未启用的字段不在输出契约里出现。"""
    rules = ["- 只在正文确实有变化时才更新，不要凭空发明。"]
    schema_lines: list[str] = []
    if advance_foreshadows:
        rules.append("- 已埋伏笔：若本段让它更接近揭晓→ advanced；被揭破/兑现→ paid_off；否则仍 planted。")
        rules.append("- new_foreshadows：仅当本段明确埋下新伏笔时才给，否则留空数组。")
        schema_lines.append('"foreshadow_updates": [{"text": "<现有伏笔文案>", "status": "planted|advanced|paid_off"}],')
        schema_lines.append('"new_foreshadows": ["..."]')
    if advance_characters:
        rules.append("- character_updates：仅当角色本段有方向/关系/目标变化时更新；新登场的角色列出完整字段。")
        schema_lines.append(
            '"character_updates": [{"name":"...","goal":"...","flaw":"...","trait":"...","note":"本段动向"}],')
    if advance_relations:
        rules.append(
            "- relation_updates：仅当本段明确建立、改变或斩断了某段关系时才给；否则留空数组。\n"
            "  a/b 用规范全名（对应角色名或势力名）；新增/改变给 label 与 note；关系断裂用 status:\"severed\"。")
        schema_lines.append(
            '"relation_updates": [{"a":"...","b":"...","label":"师徒/宿敌/同盟...","note":"...",\n'
            '                        "status":"new|changed|severed"}],')
    joined_schema = "\n  ".join(schema_lines)
    return (
        "你是叙事状态管理员。根据当前角色、伏笔账本、关系账本与刚写的一段新正文，"
        "产出本次的状态更新。\n要求：\n"
        + "\n".join(rules) +
        "\n严格只输出一个 JSON 对象，不要解释：\n{\n  "
        + joined_schema.rstrip(",\n") +
        "\n}\n只列出有变化或新增的项，稳定的内容一律省略；未启用的字段一律不要出现。"
    )


@dataclass
class AdvancePlan:
    """本次决策应推进哪些账本。低浓度过场默认只推关系，不惊动伏笔。"""

    advance_characters: bool = True
    advance_foreshadows: bool = True
    advance_relations: bool = True
    _hint: str = field(default="", repr=False)

    @property
    def any(self) -> bool:
        return self.advance_characters or self.advance_foreshadows or self.advance_relations


def _build_user(*, premise: str, synopsis: str, characters: list, foreshadows: list,
                relations: list, passage: str) -> str:
    char_lines = "\n".join(
        f"- {c['name']}({'主角' if c.get('role') == 'protagonist' else '配角'}，目标 {c.get('goal') or '未知'})"
        for c in characters if c.get("name")
    )
    st = {"planted": "已埋", "advanced": "推进中", "paid_off": "已兑现"}
    fs_lines = "\n".join(
        f"- {f['text']}（{st.get(f.get('status'), f.get('status'))}）"
        for f in foreshadows if f.get("text")
    )
    rel_lines = "\n".join(
        f"- {r.get('a')} {r.get('label') or '与'} {r.get('b')}"
        f"（{r.get('note') or ''}）" if r.get("a") and r.get("b") else ""
        for r in relations
    )
    return (
        f"【故事前提】{premise}\n【故事简介】{synopsis}\n"
        f"【当前角色】\n{char_lines or '（暂无）'}\n"
        f"【伏笔账本】\n{fs_lines or '（暂无）'}\n"
        f"【关系账本】\n{rel_lines or '（暂无）'}\n"
        f"【新写正文】\n{passage}\n"
        "请输出状态更新 JSON："
    )


def _apply_foreshadows(foreshadows: list, updates: list) -> list:
    text_to_fs: dict[str, int] = {}
    for i, f in enumerate(foreshadows):
        text_to_fs.setdefault(f["text"], i)
    for u in updates or []:
        text = (u.get("text") or "").strip()
        status = u.get("status")
        if text in text_to_fs and status in _FORESHADOW_STATUSES:
            foreshadows[text_to_fs[text]]["status"] = status
    return foreshadows


def _add_new_foreshadows(foreshadows: list, seeds: list) -> list:
    existing = {f["text"] for f in foreshadows}
    for s in seeds or []:
        raw = str(s).strip()
        if raw and raw not in existing:
            foreshadows.append({"id": f"fs-{len(foreshadows) + 1}", "text": raw,
                                "origin": "剧情推进", "status": "planted"})
            existing.add(raw)
    return foreshadows


def _apply_characters(characters: list, updates: list) -> list:
    by_name = {c["name"]: c for c in characters}
    for u in updates or []:
        name = (u.get("name") or "").strip()
        if not name:
            continue
        entry = by_name.get(name)
        if entry is None:
            entry = {"name": name, "role": u.get("role", "supporter"), "goal": u.get("goal") or "",
                     "inner_need": u.get("inner_need") or "", "flaw": u.get("flaw") or "",
                     "trait": u.get("trait") or ""}
            by_name[name] = entry
            characters.append(entry)
        for k in ("role", "goal", "inner_need", "flaw", "trait"):
            if u.get(k):
                entry[k] = u[k]
        if u.get("note"):
            moves = entry.setdefault("moves", [])
            if u["note"] not in moves:
                moves.append(u["note"])
    return characters


def _rel_key(a: str, b: str) -> tuple[str, str]:
    """无向边规范键：a/b 排序归一，同一对实体只保留一条边。"""
    return (min(a, b), max(a, b))


def _apply_relations(relations: list, updates: list) -> list:
    """把增量 relation_updates 合并进关系账本。

    新增/改变 → upsert（排序归一避免 A-B / B-A 重复）；status:"severed" → 移除该边。
    返回新列表，不原地改入参。
    """
    rel = list(relations)
    by_key: dict[tuple[str, str], int] = {_rel_key(r["a"], r["b"]): i for i, r in enumerate(rel)}
    for u in updates or []:
        a = (u.get("a") or "").strip()
        b = (u.get("b") or "").strip()
        if not a or not b or a == b:
            continue
        key = _rel_key(a, b)
        if (u.get("status") or "") == "severed":
            if key in by_key:
                rel.pop(by_key[key])
                by_key = {_rel_key(r["a"], r["b"]): i for i, r in enumerate(rel)}
            continue
        label = (u.get("label") or "").strip()
        note = (u.get("note") or "").strip()
        if key in by_key:
            i = by_key[key]
            if label:
                rel[i]["label"] = label
            if note:
                rel[i]["note"] = note
        else:
            rel.append({"a": key[0], "b": key[1], "label": label, "note": note})
    return rel


class NarrativeUpdater:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def advance_plan(self, *, kind: DirectionKind, passage: str,
                     characters: list, foreshadows: list) -> AdvancePlan:
        """按剧情浓度决定本次推进哪些账本。

        高浓度（EVENT/ACTION/MEETING/FORESHADOW/CUSTOM）→ 三账本全推。
        低浓度（SCENE 过场）→ 触及实体名才推关系；不惊动伏笔，也不凭空改角色；
        纯过渡且未触及任何角色/伏笔 → 全部跳过，省一次 LLM 调用。
        """
        blob = passage or ""
        names = [c["name"] for c in characters if c.get("name")]
        fs_texts = [f["text"] for f in foreshadows if f.get("text")]
        hit = any(t and t in blob for t in names + fs_texts)

        if kind in _HIGH_CONCENTRATION_KINDS:
            return AdvancePlan(
                advance_characters=True, advance_foreshadows=True, advance_relations=True,
                _hint="高浓度决策：三账本全推",
            )
        # SCENE 过场
        if not hit:
            return AdvancePlan(
                advance_characters=False, advance_foreshadows=False, advance_relations=False,
                _hint="纯场景过渡且未触及既定设定，跳过状态更新",
            )
        return AdvancePlan(
            advance_characters=hit, advance_foreshadows=False, advance_relations=True,
            _hint="过场但触及实体名：只推进关系，不惊动伏笔",
        )

    async def update(self, *, premise: str, synopsis: str, characters: list,
                     foreshadows: list, relations: list, passage: str,
                     advance_characters: bool = True, advance_foreshadows: bool = True,
                     advance_relations: bool = True) -> tuple[list, list, list]:
        """返回 (新characters, 新foreshadows, 新relations)；解析失败或上游异常则原样返回。

        未启用的账本不参与解析落账，保持原样。
        """
        user = _build_user(premise=premise, synopsis=synopsis, characters=characters,
                           foreshadows=foreshadows, relations=relations, passage=passage)
        system = _narrative_system(
            advance_characters=advance_characters,
            advance_foreshadows=advance_foreshadows,
            advance_relations=advance_relations,
        )
        try:
            raw = await self._gateway.complete(task="narrative_update", system=system, user=user)
            data = loads_coerce(raw)
            if not isinstance(data, dict):
                return characters, foreshadows, relations
        except Exception:
            return characters, foreshadows, relations

        new_fs = list(foreshadows)
        if advance_foreshadows:
            new_fs = _add_new_foreshadows(
                _apply_foreshadows(new_fs, data.get("foreshadow_updates") or []),
                data.get("new_foreshadows") or [],
            )
        new_chars = _apply_characters(list(characters), data.get("character_updates") or []) \
            if advance_characters else list(characters)
        new_rels = _apply_relations(list(relations), data.get("relation_updates") or []) \
            if advance_relations else list(relations)
        return new_chars, new_fs, new_rels