"""去 AI 味静态规则扫描。

规则借鉴 llmlint / storyforge anti-ai 的分类思想，逐条匹配已知的"AI 腔"模式：
- block：模板感重，通常应改写
- warn ：密度过高/较模板化，建议微调

返回可 JSON 序列化的 dict 列表（便于直接进 API 响应）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class _Rule:
    name: str
    severity: str  # "block" | "warn"
    pattern: re.Pattern[str]
    reason: str
    suggestion: str
    threshold: int = 1  # 出现达到该次数才报告（>1 为"密度"规则）


def _word_rule(name: str, severity: str, words: list[str], reason: str, suggestion: str) -> _Rule:
    return _Rule(name=name, severity=severity, pattern=re.compile(
        "(?:^|[，。；、\s])(" + "|".join(re.escape(w) for w in words) + ")",
    ), reason=reason, suggestion=suggestion)


def _freq_rule(name: str, words: list[str], threshold: int,
               reason: str, suggestion: str, severity: str = "warn") -> _Rule:
    return _Rule(name=name, severity=severity, pattern=re.compile(
        "(?<![A-Za-z])(" + "|".join(re.escape(w) for w in words) + ")(?![A-Za-z])",
    ), threshold=threshold, reason=reason, suggestion=suggestion)


RULES: list[_Rule] = [
    # block 级：模板/空话味重
    _word_rule("meta-summary", "block", ["总的来说", "总而言之", "值得一提的是", "不难发现",
                                          "众所周知", "让我们看看", "值得注意的是"],
               "空泛总结/元语言，AI 腔重", "删去或用具体动作/场景代替"),
    _word_rule("tautology", "block", ["真正的勇敢", "果然不愧是", "一定是上天安排", "命运自有安排"],
               "套话/鸡汤句式", "落到一个具体的抉择或后果"),
    # warn 级：密度过高
    _freq_rule("filler", ["简直", "居然", "竟然", "未免", "分明"], 2,
               "高值感叹词使用过密", "删减或用更克制的表达"),
    _freq_rule("transition-word", ["然而", "与此同时", "转眼间", "不过转眼"], 3,
               "机械过渡词堆叠", "多用动作/时间承接代替"),
    _freq_rule("emotional-tag", ["他忍不住想", "她忍不住想", "他不由想", "她不由想", "他心里想",
                                 "他感到", "她感到"], 3,
               "过度心理解说/情感标签化", "用动作、神态、对白体现，而非直接点名情绪"),
    _freq_rule("rhetorical-question", ["难道不", "难道不是", "怎么可以", "怎么能够"], 2,
               "公式化反问", "保留必要处，删冗余"),
]


def scan(text: str) -> list[dict]:
    """对正文扫描，返回 lint 问题列表（severity 高者在前，最多 24 条）。"""
    issues: list[dict] = []
    for rule in RULES:
        if rule.threshold > 1:
            count = len(rule.pattern.findall(text))
            if count < rule.threshold:
                continue
            _append_text(issues, rule, count)
        else:
            for m in rule.pattern.finditer(text):
                frag = (m.group(1) or m.group(0))[:24].strip()
                _append(issues, rule, frag)
    issues.sort(key=lambda d: (0 if d["severity"] == "block" else 1, ))
    return issues[:24]


def _append(issues: list[dict], rule: _Rule, fragment: str) -> None:
    issues.append({
        "rule": rule.name, "severity": rule.severity,
        "fragment": fragment, "reason": rule.reason, "suggestion": rule.suggestion,
    })


def _append_text(issues: list[dict], rule: _Rule, count: int) -> None:
    issues.append({
        "rule": rule.name, "severity": rule.severity,
        "fragment": f"出现 {count} 次", "reason": rule.reason, "suggestion": rule.suggestion,
    })


# ---- 供测试/文档用的规则清单 ----
def rule_names() -> list[str]:
    return [r.name for r in RULES]