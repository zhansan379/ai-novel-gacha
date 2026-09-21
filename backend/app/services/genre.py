"""题材引导：轻量题材识别 + 反模式约束 + 正文题材卡资产。

数据来源（均 MIT，已在 app/assets/genre_cards/ 保留来源说明）：
- 反模式 / 节奏 / 典型分幕：移植自 storyforge `src/lib/ai/genre-metadata.ts`
  （原 TS 数据改写成 dataclass，内容未改动；构造 `【题材约束】…` 块的口径与其
  `buildGenreConstraintContext` 一致）。
- 正文题材卡：直接拷贝 oh-story-claudecode
  `skills/story-long-write/references/genre-prose-cards/*.md`，作为按题材注入的正文参考。
  storyforge 未覆盖的题材（军事/体育/诸天等），反模式取自对应题材卡的「禁止漂移」段。

只做两件事，十分克制：
- resolve_genres()：从前提文本识别主题材（关键词匹配，无 LLM），默认只召回 1 个
  （对齐 oh-story「只召回一张、别整套载入」）。
- genre_constraint_text()：把命中的题材反模式 + 节奏拼成一段提示词块，供生成注入。
  题材约束是柔性的「避免」，与硬性的「真实事实基座」层级不同，注入时放在其后。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_GENRE_CARD_DIR = Path(__file__).resolve().parents[1] / "assets" / "genre_cards"


@dataclass(frozen=True)
class GenreSpec:
    id: str
    label: str
    keywords: tuple[str, ...]                    # 前提命中任一即识别
    anti_patterns: tuple[str, ...]               # 「避免…」
    pacing: str = ""                              # 节奏策略
    structure: tuple[tuple[str, str], ...] = ()   # (篇, 描述) 典型分幕，喂大纲/蓝图
    card_file: str = ""                           # 正文题材卡文件名（无则空）


# 题材注册表。keywords 为中文识别词，按与用户题材清单的对应关系收敛（言情/末世/种田
# 保留为可用扩展，其余取自 storyforge metadata + oh-story 卡）。
GENRE_SPECS: tuple[GenreSpec, ...] = (
    GenreSpec(
        id="xuanhuan", label="玄幻",
        keywords=("玄幻", "修炼", "境界", "灵气", "修士", "宗门", "飞升", "渡劫", "修仙", "大能"),
        anti_patterns=(
            "避免无脑升级无剧情", "避免反派智商下线", "避免设定前后矛盾", "避免战斗只靠数值碾压",
            "避免堆等级表与境界名词", "避免空喊热血", "避免无代价突破",
        ),
        pacing="升级-战斗-探索三段式循环，每10章一个小高潮，每卷一个大决战",
        structure=(("崛起", "废柴逆袭、获得机缘、初入江湖"), ("争雄", "势力冲突、实力飞跃、结交盟友"),
                   ("称霸", "更高层面的较量、揭开世界真相"), ("巅峰", "终极挑战、突破极限、封神或超脱")),
        card_file="传统玄幻",
    ),
    GenreSpec(
        id="xianxia", label="仙侠",
        keywords=("仙侠", "道法", "仙尊", "炼丹", "剑修", "体修", "上界", "真仙", "问道"),
        anti_patterns=(
            "避免过度堆砌境界名称", "避免\"踩脸打脸\"循环套路", "避免丹药/法宝无限叠加",
            "避免女性角色沦为附庸", "避免把修行写成等级刷怪", "避免反派脸谱化",
        ),
        pacing="前期慢节奏铺垫世界观和人物关系，中期交替升级与探索，每卷末设置\"天劫/大考验\"高潮",
        structure=(("入门", "凡人机缘、拜师入门、初识修行"), ("历练", "门派试炼、结识同伴、初露锋芒"),
                   ("争锋", "宗门大比、敌对势力、实力飞跃"), ("风云", "更大的世界、隐藏的秘密、力量蜕变"),
                   ("飞升", "终极对决、大道抉择、飞升或超脱")),
        card_file="东方仙侠",
    ),
    GenreSpec(
        id="xifan", label="奇幻",
        keywords=("奇幻", "魔法", "剑与魔法", "精灵", "巨龙", "巫师", "法师", "西方大陆", "吟游诗人", "冒险者"),
        anti_patterns=(
            "避免魔法体系无规则", "避免种族设定只是换皮人类", "避免任务过于游戏化",
            "避免只堆设定而缺少人物选择",
        ),
        pacing="冒险-休整交替，每个区域/地牢为一个节奏单元，史诗战争为全书高潮",
        structure=(("启程", "接受使命、组建冒险队伍"), ("历险", "穿越不同地域、遭遇挑战与诱惑"),
                   ("深渊", "至暗时刻、队伍分裂或牺牲"), ("决战", "终极对决、拯救世界或改变格局")),
        card_file="西方奇幻",
    ),
    GenreSpec(
        id="wuxia", label="武侠",
        keywords=("武侠", "江湖", "侠", "门派", "内力", "武林", "刀剑", "恩怨", "师门"),
        anti_patterns=(
            "避免武功等级过于量化", "避免正邪二元对立过于简单", "避免忽视江湖规矩与人情世故",
        ),
        pacing="以事件驱动节奏，恩怨交替推进，关键打斗浓墨重彩",
        structure=(("出山", "少年入江湖、师门传承、初遇恩怨"), ("闯荡", "行走江湖、结识群侠、卷入纷争"),
                   ("风波", "武林大会、门派争锋、身世揭秘"), ("归隐", "最终决战、了却恩仇、归隐或传承")),
    ),
    GenreSpec(
        id="dushi", label="都市",
        keywords=("都市", "职场", "公司", "豪门", "总裁", "城", "市区", "上班族", "白领", "商战"),
        anti_patterns=(
            "避免主角万能无短板", "避免女角色只做花瓶", "避免脱离现代社会常识",
            "避免霸道总裁千篇一律的人设", "避免误会推动全部剧情", "避免硬塞异能/系统",
        ),
        pacing="事件驱动为主，日常与危机交替，感情线穿插其中调节节奏",
        structure=(("起步", "主角的日常困境与转折机遇"), ("发展", "逐步崛起、人际网络扩展"),
                   ("危机", "重大挑战、对手出现、内外压力"), ("巅峰", "终极对决、事业与感情的抉择")),
        card_file="都市日常",
    ),
    GenreSpec(
        id="realism", label="现实",
        keywords=("现实", "纪实", "年代", "山村", "农村", "小镇", "生活流", "普通人", "时代"),
        anti_patterns=(
            "避免脱离现实的巧合", "避免说教性过强的叙述", "避免人物行为不符合社会背景",
            "避免忽视细节真实感",
        ),
        pacing="整体平稳推进，关键节点适度加速，用日常细节积蓄情感张力",
        structure=(("日常", "建立人物的日常生活与困境"), ("变化", "打破平衡的事件，推动人物做出选择"),
                   ("挣扎", "矛盾深化，内心与外部冲突交织"), ("蜕变", "人物在困境中成长或妥协的结局")),
        card_file="都市日常",
    ),
    GenreSpec(
        id="junshi", label="军事",
        keywords=("军事", "战场", "军营", "部队", "战役", "军官", "士兵", "武器", "打仗", "谍战", "战场"),
        anti_patterns=(
            "不要把军事写成纯爽战斗", "不要让情报靠旁白发放", "不要忽略身份暴露代价",
            "不要把历史危险写轻", "避免无视后勤/编制/伤亡逻辑",
        ),
        pacing="行动驱动节奏，情报/作战交替，身份与筹码的代价贯穿全程",
        card_file="抗战谍战",
    ),
    GenreSpec(
        id="lishi", label="历史",
        keywords=("历史", "朝代", "皇帝", "王朝", "权谋", "将士", "君臣", "宫廷", "古代", "考据", "架空改"),
        anti_patterns=(
            "避免严重违背历史常识（非架空时）", "避免现代思维套用古人", "避免朝堂戏过于脸谱化",
            "避免主角全知先知",
        ),
        pacing="大事件为节奏锚点，日常铺垫与朝堂博弈交替，战争场面集中爆发",
        structure=(("入局", "主角进入权力核心、初识格局"), ("布局", "政治博弈、结盟对抗、暗流涌动"),
                   ("变局", "重大转折、战争或政变、命运抉择"), ("定局", "天下大势已定、功过评说")),
        card_file="历史古代",
    ),
    GenreSpec(
        id="youxi", label="游戏",
        keywords=("游戏", "副本", "玩家", "虚拟网游", "竞技", "攻略", "公会", "打怪", "掉落", "版本"),
        anti_patterns=(
            "避免数值设定过于复杂难懂", "避免游戏外完全没有生活", "避免技能只是换名的魔法",
            "避免写成数值表", "避免只有技能名没有操作",
        ),
        pacing="副本/赛事为节奏单元，训练-比赛循环，游戏内外双线交叉",
        structure=(("入坑", "接触游戏、发现天赋、加入队伍"), ("训练", "磨练技术、探索系统、团队磨合"),
                   ("赛场", "正式比赛/排位、遭遇强敌"), ("巅峰", "冠军争夺或终极副本挑战")),
        card_file="游戏体育",
    ),
    GenreSpec(
        id="tiyu", label="体育",
        keywords=("体育", "比赛", "球场", "赛事", "训练", "联赛", "夺冠", "竞技", "运动员", "教练"),
        anti_patterns=(
            "不要写成数值表", "不要只有技能名没有操作", "不要让队友和观众反应同质化",
            "不要把比赛胜负写成纯旁白宣布",
        ),
        pacing="训练-比赛循环为节奏单元，赛场内外压力与成长交替推进",
        card_file="游戏体育",
    ),
    GenreSpec(
        id="scifi", label="科幻",
        keywords=("科幻", "未来", "星际", "外星", "AI", "人工智能", "虚拟", "黑科技", "时间线", "太空", "机器人", "芯片"),
        anti_patterns=(
            "避免伪科学解释核心设定", "避免技术万能论", "避免忽视社会变革对人的影响",
            "避免科技只当名词不落成代价", "避免硬贴黑科技换皮",
        ),
        pacing="探索-发现-危机三段循环，科技设定穿插展开，避免信息倾倒",
        structure=(("发现", "科技突破或异常现象、引出核心设定"), ("探索", "深入未知、团队组建、世界观展开"),
                   ("危机", "技术失控或外来威胁、人性考验"), ("抉择", "终极博弈、科技与人性的平衡")),
        card_file="科幻末世",
    ),
    GenreSpec(
        id="wuxian", label="诸天无限",
        keywords=("诸天", "无限流", "快穿", "万界", "多个世界", "穿梭世界", "副本世界", "综漫", "平行世界"),
        anti_patterns=(
            "避免副本之间毫无联系", "避免队友只是消耗品", "避免主角独狼通关",
            "不要每个世界开头模板化报剧情", "不要让主角只靠知道原文躺赢", "不要忘记当前世界的情绪重量",
        ),
        pacing="副本/世界为单元节奏，每个世界内紧凑推进，世界间休整期发展人物关系",
        structure=(("新手世界", "规则建立、团队初组、基础生存"), ("成长世界", "难度升级、策略深化、团队磨合"),
                   ("高难世界", "死亡威胁、背叛与信任、终极挑战"), ("终局", "揭示幕后真相、逃脱或超越")),
        card_file="快穿",
    ),
    GenreSpec(
        id="xuanyi", label="悬疑灵异",
        keywords=("悬疑", "灵异", "惊悚", "怪谈", "推理", "失踪", "命案", "侦探", "鬼", "民俗", "医院", "谋杀"),
        anti_patterns=(
            "避免凶手身份过早暴露", "避免线索出现但不回收", "避免超自然解释代替逻辑推理",
            "避免侦探角色全知全能", "避免怪物出场即讲满规则", "避免只吓人不推进规则",
        ),
        pacing="节奏由松到紧，前1/3铺设谜面+误导，中段反转，尾段加速揭示真相；恐惧来自有限视角与代价升级",
        structure=(("谜面", "案件发生、角色登场、表面线索展示"), ("调查", "深入挖掘、嫌疑人盘查、伏笔布局"),
                   ("误导", "假象破灭、新线索出现、视角反转"), ("真相", "逻辑推演、揭开谜底、收束伏笔")),
        card_file="悬疑灵异",
    ),
    GenreSpec(
        id="qingxiaoshuo", label="轻小说",
        keywords=("轻小说", "日式", "校园社团", "异世界转生", "开后宫", "萌", "中二", "冒险日常"),
        anti_patterns=(
            "避免角色标签化堆人设", "避免日常流水账无重点", "避免自嗨而没有读者向的欢愉",
        ),
        pacing="单元事件推进，日常与冒险交替，节奏轻快、信息密度低",
    ),
    GenreSpec(
        id="yanqing", label="言情",
        keywords=("言情", "恋爱", "爱情", "CP", "甜", "虐", "心动", "分手", "暗恋", "婚恋"),
        anti_patterns=(
            "避免\"霸道总裁\"千篇一律的人设", "避免误会推动全部剧情", "避免配角沦为工具人",
            "避免感情线没有成长弧",
        ),
        pacing="甜虐交替节奏，3章甜1章虐为基础节奏，每卷有一次大危机考验感情",
        structure=(("相遇", "命运交汇、初印象反差、暗生情愫"), ("靠近", "日常互动、心理博弈、感情升温"),
                   ("危机", "误解/外力介入、分离、内心挣扎"), ("重逢", "真相大白、坦诚相待、感情升华")),
    ),
    GenreSpec(
        id="moshi", label="末世",
        keywords=("末世", "末日", "丧尸", "废土", "灾变", "幸存者", "避难所", "资源求生"),
        anti_patterns=(
            "避免主角独善其身不需要队伍", "避免资源问题无限忽略", "避免丧尸/怪物只是背景板",
        ),
        pacing="紧张-喘息交替节奏，每次探索带来新危机，安全区域作为缓冲段",
        structure=(("末日降临", "灾变发生、主角求生、组建小队"), ("废土求生", "探索废墟、争夺资源、人性博弈"),
                   ("势力纷争", "避难所冲突、阵营选择、信任危机"), ("希望曙光", "找到出路或接受新世界")),
        card_file="科幻末世",
    ),
    GenreSpec(
        id="zhongtian", label="种田",
        keywords=("种田", "经营", "建设", "发展建设", "领地", "庄园", "家业", "屯田"),
        anti_patterns=(
            "避免建设过于轻松无阻力", "避免完全没有外部冲突", "避免经济系统不合理",
        ),
        pacing="建设与挑战交替，每个阶段有新的发展目标和对应危机，整体偏慢但不无聊",
        card_file="都市种田",
    ),
)

# 关键词 → 题材的倒排缓存（启动时构建一次）
_WORD_INDEX: dict[str, GenreSpec] | None = None


def _index() -> dict[str, GenreSpec]:
    global _WORD_INDEX
    if _WORD_INDEX is None:
        _WORD_INDEX = {}
        for spec in GENRE_SPECS:
            for kw in spec.keywords:
                _WORD_INDEX.setdefault(kw, spec)
    return _WORD_INDEX


def resolve_genres(text: str, *, explicit: str = "", cap: int | None = None) -> list[GenreSpec]:
    """从前提识别主题材。explicit 为显式题材名；否则用 contextvar current_genre_label
    （开书 profiling LLM 判定）优先；最后关键词扫文本。优先级：explicit > profiling > 关键词。

    cap=命中题材上限，默认取 settings.genre_max_recall（未配置时 1），对齐 oh-story 只召回一张。
    """
    from app.config import settings
    from app.context import current_genre_label
    if cap is None:
        cap = getattr(settings, "genre_max_recall", 1) or 1
    normalized = re.sub(r"\s+", "", (text or ""))
    idx = _index()
    out: list[GenreSpec] = []
    # 1) 显式题材：按 label 前缀对齐省去二次关键词
    if explicit:
        e = re.sub(r"\s+", "", explicit)
        for spec in GENRE_SPECS:
            if spec.label in e or e in spec.label:
                if spec not in out:
                    out.append(spec)
    # 2) profiling LLM 判定的题材（比关键词准）：按 label/id 对齐
    profiled = (current_genre_label.get() or "").strip()
    if profiled:
        e = re.sub(r"\s+", "", profiled)
        for spec in GENRE_SPECS:
            if re.sub(r"\s+", "", spec.label) in e or e in re.sub(r"\s+", "", spec.label) or spec.id == profiled:
                if spec not in out:
                    out.append(spec)
    # 3) 关键词召回：命中顺序即优先级，去重
    for kw in idx:
        if kw in normalized:
            spec = idx[kw]
            if spec not in out:
                out.append(spec)
    if not out:
        return []
    # explicit 命中的排在关键词之前（用户显式指定优先）
    return out[:cap]


def genre_constraint_text(specs: list[GenreSpec]) -> str:
    """把命中题材拼成提示词块：反模式 + 节奏策略（对齐 storyforge buildGenreConstraintContext）。"""
    if isinstance(specs, GenreSpec):  # 容错：允许传单个题材
        specs = [specs]
    if not specs:
        return ""
    blocks: list[str] = []
    for spec in specs:
        parts = [f"【题材约束：{spec.label}】"]
        if spec.anti_patterns:
            parts.append(f"反模式（请避免）：{'；'.join(spec.anti_patterns)}")
        if spec.pacing:
            parts.append(f"节奏策略：{spec.pacing}")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def structure_hint(specs: list[GenreSpec]) -> str:
    """典型分幕（喂蓝图/大纲生成），没有则空串。"""
    if isinstance(specs, GenreSpec):  # 容错：允许传单个题材
        specs = [specs]
    rows = []
    for spec in specs:
        if not spec.structure:
            continue
        parts = "，".join(f"{t}：{d}" for t, d in spec.structure)
        rows.append(f"（{spec.label}参考分幕）{parts}")
    return "\n".join(rows)


def card_text(spec: GenreSpec) -> str:
    """读取正文题材卡原文（以卡文件为准；缺失返回空串）。供正文/方向注入用的详细参考。"""
    if not spec.card_file:
        return ""
    path = _GENRE_CARD_DIR / f"{spec.card_file}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except (IOError, OSError):
        return ""
    # 去掉 frontmatter，只保留正文卡内容
    if text.startswith("---"):
        _, _, body = text.partition("\n---\n")
        return body.strip() if body else text.strip()
    return text.strip()


def available_cards() -> list[str]:
    """所有可用题材卡名（供调试/展示）。"""
    if not _GENRE_CARD_DIR.is_dir():
        return []
    return sorted(p.stem for p in _GENRE_CARD_DIR.glob("*.md") if p.stem != "README")