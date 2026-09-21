"""题材卡：全量索引 / 单卡详情 / 蓝图命中 冒烟测试。"""
from app.services.genre import (
    GENRE_SPECS,
    available_cards,
    card_detail_by,
    card_index,
    resolve_genres,
)


def test_card_index_covers_all_directory_cards():
    """索引要覆盖 genre_cards/ 目录里全部卡，且每张都有 id/label/card_title。"""
    idx = card_index()
    assert idx, "题材卡目录不应为空"
    titles = {c["card_title"] for c in idx}
    assert titles == set(available_cards())
    for c in idx:
        assert c["id"] and c["label"] and c["card_title"]


def test_card_index_matches_owner_spec():
    """每个卡文件对应首个注册归属，id/label 一致（多题材共用一张卡时取首者）。"""
    by_title = {c["card_title"]: c for c in card_index()}
    seen = set()
    for spec in GENRE_SPECS:
        if not spec.card_file or spec.card_file in seen:
            continue
        seen.add(spec.card_file)
        card = by_title[spec.card_file]
        assert card["id"] == spec.id
        assert card["label"] == spec.label


def test_card_detail_by_shared_card_keeps_spec_identity():
    """共用卡文件的题材按各自 id 取详情，身份不混淆（都市 vs 现实 都指向都市日常）。"""
    for gid in ("dushi", "realism"):
        d = card_detail_by(gid)
        assert d["id"] == gid
        assert d["card_title"] == "都市日常"
        assert d["body"]


def test_card_detail_by_returns_full_body():
    """单卡详情要能读到正文参考原文（含 frontmatter 已剥离）。"""
    detail = card_detail_by("xuanhuan")
    assert detail["id"] == "xuanhuan"
    assert detail["label"] == "玄幻"
    assert detail["card_title"] == "传统玄幻"
    assert detail["anti_patterns"]
    assert detail["pacing"]
    assert detail["body"] and not detail["body"].startswith("---")


def test_card_detail_by_unregistered_title():
    """目录里有、GENRE_SPECS 未注册的卡以标题兜底，仍能读到正文。"""
    idx = card_index()
    orphan = next((c for c in idx if c["id"] == c["card_title"]), None)
    if orphan:  # 仅当存在未注册卡时才校验
        d = card_detail_by(orphan["id"])
        assert d["id"] == orphan["id"]
        assert d["body"]


def test_resolve_genres_hits_card():
    """前提含题材关键词时能命中注册题材。"""
    specs = resolve_genres("主角当众穿越到修真界，拜入宗门开始修炼")
    assert any(s.id == "xuanhuan" for s in specs)