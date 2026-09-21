"""叙事状态更新（NarrativeUpdater）：每次决策正文生成后推进伏笔 / 增量更新角色 / 关系。

- 把"当前角色 + 伏笔账本 + 关系账本 + 新写正文"交给 LLM，产出紧凑 JSON 状态更新。
- 伏笔推进/回收（planted → advanced → paid_off）、可新埋；角色可增量改或新登场。
- advance_plan 做差分门控：按剧情浓度决定本次推进哪些账本（低浓度过场只推进关系，
  不惊动伏笔），并把"是否启用某账本"传进 update 的提示词与落账逻辑。
- 宽容处理：update 的真实失败（网关异常 / 解析失败）会向上抛，由 story_service 重试；
  重试耗尽后静默跳过，绝不因为这次辅助更新影响正文生成。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.llm import LLMGateway
from app.llm.errors import ModelError
from app.schemas import DirectionKind
from app.services.jsonparse import loads_coerce

_FORESHADOW_STATUSES = {"planted", "advanced", "paid_off"}

# 高浓度档：全面推进三账本；低浓度档（SCENE 过场）只推关系，不惊动伏笔/不凭空改角色
_HIGH_CONCENTRATION_KINDS = {
    DirectionKind.EVENT, DirectionKind.ACTION, DirectionKind.MEETING,
    DirectionKind.FORESHADOW, DirectionKind.CUSTOM,
}

_APPEARANCE_SYSTEM = """你是中文小说「出场人物识别器」。从一段正文里找出所有"有名有姓地出场"的具体人物名字
（中文姓名，如"林浩""李健国"；含以称呼名稳定指代同一人的，如"掌柜老王"），供世界观出场人物建档。

判断标准只有一个：这确实是正文里某个具体人的名字或专属称谓。严格排除——
- 泛称 / 职业 / 身份 / 亲属称呼：警察、老板、少年、老者、掌柜、师爷、妈、哥、读者、众人
- 地名 / 机构 / 势力名：雾海旧城、守刻人、黑市势力
- 代词：他、她、我、你、那人
- 已知人物名单里已有的人（名单外才算新出场）

严格只输出一个 JSON 字符串数组（如 ["林浩","李健国"]），不要解释、不要 markdown。拿不准的宁缺毋滥。
"""


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
                relations: list, passage: str, facts: list[str] | None = None) -> str:
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
    facts_txt = "\n".join(f"- {f}" for f in (facts or []))
    facts_block = (f"\n【真实事实（须尊重，与简介/剧情冲突时以此为准）】\n{facts_txt}"
                   if facts_txt else "")
    return (
        f"{facts_block}\n"
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


def register_appearances(appearances: list, characters: list, names: list,
                         *, passage_no: int, threshold: int) -> tuple[list, list, list, list]:
    """把识别出的新名字登记进出场账本；累计出场达 threshold 即升格为正式角色。

    正式角色（characters）进知识图谱并参与生成上下文；未达阈值的留在出场人物账本
    （appearances）。同一名字只会在其中一个账本里。返回
    (新appearances, 新characters, 新登记未升格名单, 本次升格名单)。
    """
    chars = list(characters)
    by_char = {c["name"]: c for c in chars}
    apps = list(appearances)
    by_app = {a["name"]: a for a in apps}
    registered: list[str] = []
    promoted: list[str] = []
    for name in names:
        if name in by_char:
            continue
        entry = by_app.get(name)
        if entry is None:
            entry = {"name": name, "count": 0, "first_no": passage_no}
            by_app[name] = entry
            apps.append(entry)
        entry["count"] += 1
        if entry["count"] >= threshold:
            chars.append({"name": name, "role": "supporter", "goal": "", "inner_need": "",
                          "flaw": "", "trait": ""})
            by_char[name] = chars[-1]
            apps.remove(entry)
            del by_app[name]
            promoted.append(name)
        else:
            registered.append(name)
    return apps, chars, registered, promoted


def drop_formalized_appearances(appearances: list, characters: list) -> list:
    """把已升格为正式角色（含被 narrative.update 补录为角色）的名字从出场账本里清掉。"""
    by_char = {c["name"] for c in characters}
    return [a for a in appearances if a["name"] not in by_char]


class NarrativeUpdater:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def extract_names(self, *, passage: str, known: list[str]) -> list[str]:
        """确定性辨识正文里"有名有姓出场"的人物名（区别于 update 的主观建档）。

        这是出场人物建档的判别来源：模型给出名字就登记，不判断重要程度、不要求有
        剧情变化。返回去重、排除已知人物后的名单；解析失败抛 ModelError，由调用方重试/兜底。
        """
        know_txt = "、".join(known) if known else "（无）"
        user = f"【已知人物（勿重复报）】\n{know_txt}\n【待识别正文】\n{passage}\n请输出新出场人名数组："
        raw = await self._gateway.complete(task="appearance", system=_APPEARANCE_SYSTEM,
                                           user=user, max_tokens=300)
        data = loads_coerce(raw)
        if not isinstance(data, list):
            raise ModelError(f"出场人物识别响应不是数组：{raw[:200]}")
        known_set = set(known)
        out: list[str] = []
        seen: set[str] = set()
        for item in data:
            name = str(item or "").strip()
            if name and name not in known_set and name not in seen:
                seen.add(name)
                out.append(name)
        return out

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
                     facts: list[str] | None = None,
                     advance_characters: bool = True, advance_foreshadows: bool = True,
                     advance_relations: bool = True) -> tuple[list, list, list]:
        """返回 (新characters, 新foreshadows, 新relations)。

        注意：真实失败（网关异常 / 解析不成合法对象）会向上抛异常，由调用方负责重试，
        不再在此静默吞掉——否则"模型没报更新"与"调用失败"无法区分，重试就失去意义。
        合法但无任何更新（空数组）仍是正常成功。
        """
        user = _build_user(premise=premise, synopsis=synopsis, characters=characters,
                           foreshadows=foreshadows, relations=relations, passage=passage,
                           facts=facts)
        system = _narrative_system(
            advance_characters=advance_characters,
            advance_foreshadows=advance_foreshadows,
            advance_relations=advance_relations,
        )
        raw = await self._gateway.complete(task="narrative_update", system=system, user=user)
        data = loads_coerce(raw)
        if not isinstance(data, dict):
            raise ModelError(f"叙事状态更新响应不是对象：{raw[:200]}")

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