from app.deslop import scan


def test_block_meta_summary_flagged():
    issues = scan("总的来说，他决定离开这座城市。值得一提的是，他来自远方。")
    names = {i["rule"] for i in issues}
    assert "meta-summary" in names
    assert all(i["severity"] == "block" for i in issues if i["rule"] == "meta-summary")


def test_clean_text_has_no_issues():
    clean = "他把门推开一条缝，冷风携着雨丝灌进来。"
    assert scan(clean) == []


def test_transition_word_count_triggers_warn():
    text = "然而他抬头。然而他又低头。然而谁也没说话。"
    names = {i["rule"] for i in scan(text)}
    assert "transition-word" in names


def test_filler_below_threshold_ok():
    # 只出现 1 次感叹词，低于阈值不报
    text = "他简直不敢相信自己的眼睛。"
    assert all(i["rule"] != "filler" for i in scan(text))


def test_block_issues_sort_first():
    text = "总而言之，他简直不敢相信。"
    issues = scan(text)
    assert issues  # 至少触发
    assert issues[0]["severity"] == "block"  # meta-summary 是 block，排前面