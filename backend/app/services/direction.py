"""DirectionGenerator：在分歧点调用 LLM 生成 3~5 张候选命运卡（强 schema JSON）。

模型返回无法解析时不再回退内置卡池，而是抛出 ModelError，
由全局 LLM 异常处理器规整成 502 响应，明确暴露上游质量问题。
"""
from __future__ import annotations

import json

from app.llm import LLMGateway
from app.llm.errors import ModelError
from app.schemas import Card
from app.services.jsonparse import loads_coerce

_DIRECTION_SYSTEM = """你是一款互动小说系统里的「命运卡生成器」。
根据给定的故事设定与上一段剧情，生成 3~5 张候选"命运卡"，每张卡代表一个可选的剧情方向。
要求：
- 卡面用简洁、有画面感的中文（勿写表格/Markdown）
- 覆盖不同方向：EVENT 随机事件 / ACTION 角色行动 / SCENE 场景转移 / MEETING 遇见新角色 / FORESHADOW 伏笔
- 稀有度 N|R|SR|SSR；SSR 卡必须含 risk_balance（张力 + 后续转折建议），且剧情张力明显更高
- weight(1~100) 表示相对出现概率
- 每张卡除卡面 hook 外，必须额外规划三件事，正文全靠它们才不空洞：
  · cause：这个事件为什么发生 / 破绽或线索是如何被察觉或暴露的（具体诱因，不可含糊）
  · aftermath：事件落定后对各方（主角、配角、对手、社会/机构）的影响与反应方向
  · suspense：落定后要给下一步留的悬念钩子（让读者想继续往下选）
- 若【当前设定状态】含真实事实基座，命运卡不得虚构与真实事实相悖的"事实"；确需架空改写须契合设定
- 严格只输出一个 JSON 数组，不要任何额外文字。
数组元素字段：
card_id(string,唯一) title(string≤40) content(string≤200)
label(EVENT|ACTION|SCENE|MEETING|FORESHADOW) rarity(N|R|SR|SSR) weight(int 1~100)
cause(string≤120) aftermath(string≤120) suspense(string≤120)
risk_balance(object, 仅SSR必填: {tension:int 1~10, suggested_turn:string≤80})
"""


def _parse_cards(raw: str) -> list[Card]:
    try:
        data = loads_coerce(raw)
    except json.JSONDecodeError as exc:
        raise ModelError(f"命运卡响应不是合法 JSON：{raw[:200]}") from exc
    if isinstance(data, dict):
        data = data.get("cards", [])
    try:
        cards = [Card.model_validate(obj) for obj in data]
    except Exception as exc:
        raise ModelError(f"命运卡响应不符合 schema：{raw[:200]}") from exc
    return cards


class DirectionGenerator:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def generate(self, *, premise: str, synopsis: str, tail: str, decision_no: int,
                       context: str = "", carryover: str = "") -> list[Card]:
        ctx = (f"\n【当前设定状态（须尊重；含真实事实且与简介冲突时以事实为准）】\n{context}"
               if context else "")
        cov = f"\n【需接着回收的悬念线（新卡应顺着它走或与它并行，别让设定线悬空）】\n{carryover}" if carryover else ""
        user = (
            f"{ctx}{cov}\n"
            f"【故事前提】{premise}\n"
            f"【故事简介】{synopsis}\n"
            f"【待决剧情尾巴】{tail}\n"
            f"【本次分歧节点 #{decision_no}】请输出命运卡 JSON 数组："
        )
        raw = await self._gateway.complete(task="direction", system=_DIRECTION_SYSTEM, user=user)
        cards = _parse_cards(raw)
        if not (3 <= len(cards) <= 5) or len({c.card_id for c in cards}) != len(cards):
            raise ModelError(f"命运卡数量/唯一性不合法: {len(cards)}")
        for c in cards:
            missing = [k for k in ("cause", "aftermath", "suspense") if not (getattr(c, k) or "").strip()]
            if missing:
                raise ModelError(f"命运卡缺少因果规划字段 {missing} => {c.title}: {c.content}")
        return cards