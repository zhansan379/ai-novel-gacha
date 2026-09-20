"""叙事状态更新（NarrativeUpdater）：每次决策正文生成后推进伏笔 / 增量更新角色。

- 把"当前角色 + 伏笔账本 + 新写正文"交给 LLM，产出紧凑 JSON 状态更新。
- 伏笔推进/回收（planted → advanced → paid_off）、可新埋；角色可增量改或新登场。
- 宽容处理：解析失败或上游异常时原样返回旧状态，绝不因为这次辅助更新影响正文生成。
- should_run 做变点门控：纯 SCENE 过渡且未触及任何角色/伏笔时跳过，省一次 LLM 调用。
"""
from __future__ import annotations

import json

from app.llm import LLMGateway
from app.schemas import DirectionKind

_FORESHADOW_STATUSES = {"planted", "advanced", "paid_off"}

_NARRATIVE_SYSTEM = """你是叙事状态管理员。根据当前角色、伏笔账本与刚写的一段新正文，产出一份紧凑的状态更新。
要求：
- 只在正文确实有变化时才更新，不要凭空发明。
- 已埋伏笔：若本段让它更接近揭晓→ advanced；被揭破/兑现→ paid_off；否则仍 planted。
- character_updates：仅当角色本段有方向/关系/目标变化时更新；新登场的角色列出完整字段。
- new_foreshadows：仅当本段明确埋下新伏笔时才给，否则留空数组。
严格只输出一个 JSON 对象，不要解释：
{
  "foreshadow_updates": [{"text": "<现有伏笔文案>", "status": "planted|advanced|paid_off"}],
  "character_updates": [{"name":"...","goal":"...","flaw":"...","trait":"...","note":"本段动向"}],
  "new_foreshadows": ["..."]
}
只列出有变化或新增的项，稳定的内容一律省略。"""


def _build_user(*, premise: str, synopsis: str, characters: list, foreshadows: list, passage: str) -> str:
    char_lines = "\n".join(
        f"- {c['name']}({'主角' if c.get('role') == 'protagonist' else '配角'}，目标 {c.get('goal') or '未知'})"
        for c in characters if c.get("name")
    )
    st = {"planted": "已埋", "advanced": "推进中", "paid_off": "已兑现"}
    fs_lines = "\n".join(
        f"- {f['text']}（{st.get(f.get('status'), f.get('status'))}）"
        for f in foreshadows if f.get("text")
    )
    return (
        f"【故事前提】{premise}\n【故事简介】{synopsis}\n"
        f"【当前角色】\n{char_lines or '（暂无）'}\n"
        f"【伏笔账本】\n{fs_lines or '（暂无）'}\n"
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


class NarrativeUpdater:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def should_run(self, *, kind: DirectionKind, passage: str,
                   characters: list, foreshadows: list) -> bool:
        """变点门控：纯场景过渡且未触及任何角色/伏笔 → 跳过，避免无谓的 LLM 调用。"""
        if kind != DirectionKind.SCENE:
            return True
        blob = passage or ""
        names = [c["name"] for c in characters if c.get("name")]
        fs_texts = [f["text"] for f in foreshadows if f.get("text")]
        return any(t and t in blob for t in names + fs_texts)

    async def update(self, *, premise: str, synopsis: str, characters: list,
                     foreshadows: list, passage: str) -> tuple[list, list]:
        """返回 (新characters, 新foreshadows)；解析失败或上游异常则原样返回。"""
        user = _build_user(premise=premise, synopsis=synopsis, characters=characters,
                           foreshadows=foreshadows, passage=passage)
        try:
            raw = await self._gateway.complete(task="narrative_update", system=_NARRATIVE_SYSTEM, user=user)
            data = json.loads(raw)
            if not isinstance(data, dict):
                return characters, foreshadows
        except Exception:
            return characters, foreshadows

        new_fs = _apply_foreshadows(list(foreshadows), data.get("foreshadow_updates") or [])
        new_fs = _add_new_foreshadows(new_fs, data.get("new_foreshadows") or [])
        new_chars = _apply_characters(list(characters), data.get("character_updates") or [])
        return new_chars, new_fs