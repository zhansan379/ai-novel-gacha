"""SQLite 持久化：写入后可跨实例重载（重启不丢）。"""
from app.schemas import Card, CardLabel, Rarity
from app.services.store import Decision, Story
from app.storage.sqlite import SQLiteStore


def _sample_story() -> Story:
    story = Story(id="s-persist", premise="一座每周重生的古城", synopsis="简介……")
    story.passages.append({"no": 1, "decision_no": None, "content": "开篇正文。"})
    story.passages.append({"no": 2, "decision_no": 1, "content": "第二章正文。"})
    d = Decision(no=1)
    d.mode = "gacha_draw"
    d.card_id = "x-1"
    d.applied = True
    d.cards = [Card(card_id="x-1", title="夜雨", content="雨夜有人敲门", label=CardLabel.EVENT,
                    rarity=Rarity.R, weight=50)]
    story.decisions[1] = d
    story.next_decision_no = 2
    return story


def test_save_then_reload_from_db(tmp_path):
    path = str(tmp_path / "p.db")

    a = SQLiteStore(path)
    a.save(_sample_story())
    a.close()

    # 模拟进程重启：全新 instance 从库加载
    b = SQLiteStore(path)
    reloaded = b.get("s-persist")

    assert reloaded.premise == "一座每周重生的古城"
    assert [p["content"] for p in reloaded.passages] == ["开篇正文。", "第二章正文。"]
    assert reloaded.next_decision_no == 2

    d = reloaded.decisions[1]
    assert d.applied is True
    assert d.mode == "gacha_draw"
    assert d.card_id == "x-1"
    assert d.cards[0].card_id == "x-1"
    b.close()


def test_overwrite_updates_rows(tmp_path):
    path = str(tmp_path / "p2.db")
    a = SQLiteStore(path)
    a.save(_sample_story())
    story = a.get("s-persist")
    story.passages.append({"no": 3, "decision_no": 2, "content": "追加的新段落。"})
    a.save(story)
    a.close()

    b = SQLiteStore(path)
    loaded = b.get("s-persist")
    assert len(loaded.passages) == 3
    assert loaded.passages[-1]["content"] == "追加的新段落。"
    b.close()