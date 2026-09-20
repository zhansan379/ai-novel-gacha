"""前置构建蓝图服务（BlueprintBuilder）：世界观 / 历史线 / 角色 / 伏笔种子。

不再产出"预设卷·章大纲"（大纲改为随剧情复盘，交由 timeline 表达）；初始伏笔
改由 foreshadow_seeds 直接提供。输出强 schema；模型返回无法解析时抛 ModelError，
由全局异常处理器规整成 502，不再静默回退占位。
"""
from __future__ import annotations

from app.llm import LLMGateway
from app.llm.errors import ModelError
from app.services.jsonparse import loads_coerce

_BLUEPRINT_SYSTEM = """你是小说世界构建师。基于「前提 + 简介」，产出结构化设定：
世界观（简洁，只写与故事相关的部分）、历史线（过去的重大事件与成因）、
角色（主角外在目标/内在需求/缺点 + 一位配角）、伏笔种子（故事开头就该埋下、
指向后文转折的伏笔文案列表，2~4 条）。
relationships：角色与角色、角色与势力之间彼此已知的初步关系，供关系图谱使用。

伏笔种子必须由你根据本故事的前提与简介自行拟定，紧扣故事内核（人物过往、阵营秘密、
关键物证、悬念关系等），禁止照抄提示词里的例子。

严格只输出一个 JSON 对象，不要 Markdown、不要解释，按以下字段结构（示例值请用 … 占位，
不要照抄为具体内容）：
{
  "world": {"rules": ["…"], "geography": "…", "power_system": "…",
            "factions": ["…"], "constraints": ["…"]},
  "history": [{"era": "…", "event": "…", "impact": "…"}],
  "characters": [{"name":"…","role":"protagonist|supporter","goal":"外在目标",
                  "inner_need":"内在需求","flaw":"缺点","trait":"一句话特征"}],
  "relationships": [{"a":"…","b":"…","label":"师徒/宿敌/同盟/隶属…","note":"一句话背景"}],
  "foreshadow_seeds": ["…", "…"]
}
relationships 的 a/b 至少应涵盖 characters 里的名字与 world.factions 里的势力名，
没有可确定的初关系时给空数组。"""


def _expect_obj(raw: str) -> dict:
    try:
        data = loads_coerce(raw)
    except json.JSONDecodeError as exc:
        raise ModelError(f"蓝图响应不是合法 JSON：{raw[:200]}") from exc
    if not isinstance(data, dict):
        raise ModelError("蓝图响应非对象")
    return data


def _expect_list(raw: str) -> list:
    try:
        data = loads_coerce(raw)
    except json.JSONDecodeError as exc:
        raise ModelError(f"蓝图响应不是合法 JSON：{raw[:200]}") from exc
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
    raise ModelError(f"蓝图响应应为数组：{raw[:200]}")


def _parse_blueprint(raw: str) -> dict:
    data = _expect_obj(raw)
    for key in ("world", "history", "characters", "foreshadow_seeds"):
        if key not in data:
            raise ModelError(f"蓝图缺少字段: {key}")
    return data


def _seed_grounding(grounding: str) -> str:
    return f"\n{grounding}\n" if grounding else ""


class BlueprintBuilder:
    """前置构建：既支持「单次复合调用」（legacy，book_fanout=False），
    也支持本次的分段构建——先定骨架锚点，再并行细化各切片，最后补关系账本。

    骨架锚点是所有并行分支（世界观/历史/角色/伏笔）共享的对齐基准，
    保证并发跑出的各片段彼此不跑岔；relationships 依赖角色名，故后置。
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def build(self, *, premise: str, synopsis: str, grounding: str = "") -> dict:
        """单次复合调用（legacy 回退路径）。"""
        raw = await self._gateway.complete(task="blueprint", system=_BLUEPRINT_SYSTEM,
                                           user=f"{_seed_grounding(grounding)}【前提】{premise}\n【简介】{synopsis}\n"
                                                f"请输出复合蓝图 JSON：")
        return _parse_blueprint(raw)

    # ---------------- 分段并行构建（book_fanout=True） ----------------

    async def build_skeleton(self, *, premise: str, synopsis: str, grounding: str = "") -> dict:
        """第一步：世界观骨架锚点。后续所有并行切片都以此为准，确保一致性。

        输出一个小 JSON：era（时代/年代基调一句）、world_tone（基调一句）、
        geography_brief（地理梗概一句）、power_system_brief（力量体系梗概一句）、
        factions（势力名数组）、protagonist_anchor（主角一句话定位）。
        """
        system = (
            _BLUEPRINT_SYSTEM + "\n本次先输出「世界观骨架锚点」，供后续并行细化共同对齐。"
            "严格只输出一个 JSON 对象，字段仅限："
            '{"era":"…","world_tone":"…","geography_brief":"…","power_system_brief":"…",'
            '"factions":["…"],"protagonist_anchor":"…"}。不要输出其他字段。'
        )
        raw = await self._gateway.complete(task="blueprint_skeleton", system=system,
                                           user=f"{_seed_grounding(grounding)}【前提】{premise}\n"
                                                f"【简介】{synopsis}\n请输出骨架 JSON：")
        sk = _expect_obj(raw)
        for key in ("era", "world_tone", "geography_brief", "power_system_brief", "protagonist_anchor"):
            if key not in sk:
                raise ModelError(f"骨架缺少字段: {key}")
        sk.setdefault("factions", [])
        return sk

    async def build_world(self, *, premise: str, synopsis: str, grounding: str = "",
                          skeleton: dict | None = None) -> dict:
        """世界观细节。势力名由骨架给出（factions 不在此重复），返回其余字段。"""
        system = (
            _BLUEPRINT_SYSTEM + "\n本次只输出「世界观」的 JSON 对象："
            '{"rules":["…"],"geography":"…","power_system":"…","constraints":["…"]}。'
            "势力名已由骨架给出，这里不要再输出 factions。"
        )
        user = _blueprint_user(premise, synopsis, grounding, skeleton, "请输出世界观 JSON：")
        raw = await self._gateway.complete(task="blueprint_world", system=system, user=user)
        return _expect_obj(raw)

    async def build_history(self, *, premise: str, synopsis: str, grounding: str = "",
                            skeleton: dict | None = None) -> list:
        system = _BLUEPRINT_SYSTEM + ("\n本次只输出「历史线」的 JSON 数组，元素形如 "
                                      '[{"era":"…","event":"…","impact":"…"}]，2~4 条。')
        user = _blueprint_user(premise, synopsis, grounding, skeleton, "请输出历史线 JSON 数组：")
        raw = await self._gateway.complete(task="blueprint_history", system=system, user=user)
        return _expect_list(raw)

    async def build_characters(self, *, premise: str, synopsis: str, grounding: str = "",
                               skeleton: dict | None = None) -> list:
        system = _BLUEPRINT_SYSTEM + ("\n本次只输出「角色」的 JSON 数组：主角一位 + 配角一位，元素形如 "
                                      '[{"name":"…","role":"protagonist|supporter","goal":"外在目标",'
                                      '"inner_need":"内在需求","flaw":"缺点","trait":"一句话特征"}]。'
                                      "主角身份与骨架的 protagonist_anchor 保持一致。")
        user = _blueprint_user(premise, synopsis, grounding, skeleton, "请输出角色 JSON 数组：")
        raw = await self._gateway.complete(task="blueprint_characters", system=system, user=user)
        return _expect_list(raw)

    async def build_foreshadows(self, *, premise: str, synopsis: str, grounding: str = "",
                                skeleton: dict | None = None) -> list:
        system = _BLUEPRINT_SYSTEM + ("\n本次只输出「伏笔种子」的 JSON 字符串数组，2~4 条。"
                                      "紧扣前提/简介拟定向后文转折的伏笔文案（人物过往、阵营秘密、关键物证、悬念关系等），"
                                      "禁止照抄提示词里的例子。")
        user = _blueprint_user(premise, synopsis, grounding, skeleton, "请输出伏笔种子 JSON 数组：")
        raw = await self._gateway.complete(task="blueprint_foreshadows", system=system, user=user)
        return _expect_list(raw)

    async def build_relationships(self, *, premise: str, synopsis: str, grounding: str = "",
                                  skeleton: dict | None = None, characters: list | None = None) -> list:
        """关系账本。必须覆盖 characters 里的角色名与 skeleton 的势力名；后置在角色生成后调用。"""
        chars = "\n".join(f"- 角色「{c.get('name')}」({c.get('role')})：目标 {c.get('goal')}" for c in (characters or []) if c.get("name"))
        system = _BLUEPRINT_SYSTEM + ("\n本次只输出「关系账本」的 JSON 数组，元素形如 "
                                      '[{"a":"…","b":"…","label":"师徒/宿敌/同盟/隶属…","note":"一句话背景"}]。'
                                      "a/b 应涵盖所给角色名与势力名。没有可确定关系时给空数组。")
        user = _blueprint_user(premise, synopsis, grounding, skeleton, "请输出关系账本 JSON 数组：") + (
            f"\n已知角色：\n{chars}" if chars else "")
        raw = await self._gateway.complete(task="blueprint_relationships", system=system, user=user)
        return _expect_list(raw)


def _blueprint_user(premise: str, synopsis: str, grounding: str,
                    skeleton: dict | None, prompt_end: str) -> str:
    sk = skeleton or {}
    sk_txt = (
        "【世界观骨架（须对齐）】"
        f"时代：{sk.get('era', '')}；基调：{sk.get('world_tone', '')}；"
        f"地理：{sk.get('geography_brief', '')}；力量体系：{sk.get('power_system_brief', '')}；"
        f"势力：{'、'.join(sk.get('factions') or [])}；主角定位：{sk.get('protagonist_anchor', '')}。"
    ) if skeleton else ""
    return (f"{_seed_grounding(grounding)}【前提】{premise}\n【简介】{synopsis}\n{sk_txt}\n{prompt_end}")