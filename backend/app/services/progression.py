"""章节收束 + 全书结局的轻量 LLM 判定。

在每个剧情拍（一段正文生成完成）之后调用 `judge`：
- end_chapter：本章是否在此收束（构成完整剧情节拍）；
- chapter_title：若收束，为本章拟标题；
- end_story：全书主线是否已充分收束、应就此走向结局（生成结局章并停止续写）。

设计原则与 character/foreshadow 等辅助步骤一致：
- 判定是“软”的——失败/解析异常一律回退为“不收束、不完结”，绝不阻塞正文生成；
- 章节软上下界（chapter_min/max_passages)与 hard ending 上限（ending_max_chapters）作为兜底，
  防止单章无限拖长或全书无限续写，兜底触发时以默认标题收束。
"""
from __future__ import annotations

import json

from app.config import settings
from app.llm import LLMGateway
from app.services.jsonparse import loads_coerce

_DEFAULT_VERDICT = {"end_chapter": False, "chapter_title": "", "end_story": False, "reason": "判定不可用，回退为不收束"}


def _default_title(no: int) -> str:
    return f"第{no}章"


class ProgressionService:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway
        self._settings = settings

    def _system(self) -> str:
        return (
            "你是一个互动小说系统的「章节与结局判定员」。读到刚写完的一段正文与这本书的最新剧情状态后，"
            "对两件事做出判断，并仅输出一个 JSON 对象。\n"
            "1) end_chapter（bool）：这一拍是否构成一个相对完整的剧情节拍，适合在此收束本章？"
            f"参考本章已有正文段数（单章建议 {self._settings.chapter_min_passages}~"
            f"{self._settings.chapter_max_passages} 段；段数过少通常还不该收，拖得很长则更该收）。\n"
            "2) chapter_title（string≤20字）：若 end_chapter 为 true，为本章起一个简洁、有文学性的标题（不带序号）。\n"
            "3) end_story（bool）：全书主线是否已充分收束、核心悬念与已埋伏笔基本兑付、继续写只剩狗尾续貂？"
            "**只在真正水到渠成时才置 true，宁可多写也不要提前烂尾**。end_story 为 true 时本章即为结局章，"
            "chapter_title 应对结局定名，且 end_chapter 也应同时为 true。\n"
            "严格只输出 JSON：\n"
            '{"end_chapter": bool, "chapter_title": string, "end_story": bool, "reason": string≤60}'
        )

    @staticmethod
    def _narrative_context(story) -> str:
        open_fs = [f for f in story.foreshadows if isinstance(f, dict) and f.get("status") != "paid_off"]
        cur = story.open_chapter()
        passage_count = max(0, len(story.passages) - cur.passage_from + 1)
        closed = [c for c in story.chapters if c.status == "closed"]
        lines = [
            f"第 {story.next_decision_no - 1} 个剧情拍刚写完。",
            f"当前是第 {cur.no} 章（本章已写 {passage_count} 段正文）。",
            f"全书已完成 {len(closed)} 章。",
            f"尚未兑付的伏笔 {len(open_fs)} 条。",
        ]
        if story.characters:
            lines.append("主要角色：" + "、".join(
                c.get("name", "?") for c in story.characters[-8:] if isinstance(c, dict)))
        if story.timeline:
            lines.append("最近走向：" + " → ".join(
                t.get("summary") or t.get("title") or "" for t in story.timeline[-3:] if isinstance(t, dict)))
        return "\n".join(lines)

    def _hard_verdict(self, story) -> dict | None:
        """兜底判定：命中硬约束时直接返回收束/结局，不依赖 LLM。"""
        closed = sum(1 for c in story.chapters if c.status == "closed")
        cur = story.open_chapter()
        passage_count = max(0, len(story.passages) - cur.passage_from + 1)
        if self._settings.chapters_enabled and passage_count >= self._settings.chapter_max_passages:
            return {"end_chapter": True, "chapter_title": cur.title or _default_title(cur.no),
                    "end_story": False, "reason": f"达到单章软上界（{passage_count} 段）"}
        if self._settings.ending_max_chapters > 0 and closed >= self._settings.ending_max_chapters:
            return {"end_chapter": True, "chapter_title": cur.title or _default_title(cur.no),
                    "end_story": True, "reason": f"达到 ending_max_chapters（{self._settings.ending_max_chapters} 章）"}
        return None

    async def judge(self, story, direction_spec, prose: str) -> dict:
        """返回 {"end_chapter", "chapter_title", "end_story", "reason"}。失败回退不收束。"""
        if not self._settings.chapters_enabled:
            return _DEFAULT_VERDICT

        hard = self._hard_verdict(story)
        cur = story.open_chapter()
        summary = (getattr(direction_spec, "summary", None) or "") if direction_spec is not None else ""
        user = (
            f"{self._narrative_context(story)}\n"
            f"【本拍剧情方向】{summary}\n"
            f"【本章最后一拍正文】\n{prose[:1200]}"
        )
        try:
            raw = await self._gateway.complete(task="progression", system=self._system(), user=user)
            data = loads_coerce(raw)
            if not isinstance(data, dict):
                raise ValueError("progression 判定不是对象")
            end_chapter = bool(data.get("end_chapter", False))
            end_story = bool(data.get("end_story", False))
            title = str(data.get("chapter_title") or "").strip()
            reason = str(data.get("reason") or "").strip()[:120]
        except Exception:
            if hard:
                return hard
            return _DEFAULT_VERDICT

        # LLM 判定结果之上叠加硬兜底
        if hard:
            end_chapter = True
            if hard.get("end_story"):
                end_story = True
            title = title or hard.get("chapter_title") or ""
            reason = f"{hard['reason']}" + (f"；{reason}" if reason else "")
        if end_story:
            end_chapter = True  # 结局章必然是本章收束
        if end_chapter and not title:
            title = cur.title or _default_title(cur.no)
        return {
            "end_chapter": end_chapter,
            "chapter_title": title[:20],
            "end_story": end_story,
            "reason": reason,
        }