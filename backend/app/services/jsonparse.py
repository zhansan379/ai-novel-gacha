"""健壮解析 LLM 返回的 JSON。

模型虽被要求"严格只输出一个 JSON 对象/数组"，但实际常把内容包进 ```json 代码围栏，
或在前后夹带说明文字（如"好的，伏笔种子如下："），甚至输出带缺陷的 JSON（对象/数组
尾逗号、字符串内裸换行等控制符）。直接用 json.loads 解析原始文本会抛 JSONDecodeError，
导致前置构建中断。这里按优先级依次尝试：

1. 原始文本整体解析；
2. 剥离 markdown 代码围栏后解析（ ```json ... ``` / ``` ... ``` ）；
3. 用最外层括号配平截取真正的顶层 JSON 结构再解析（会优先于从内层误抽出子数组/子对象）；
4. 对上述任一候选做容错修复（去尾逗号、转义字符串内裸控制符）后再解析。

任一成功即返回对应 Python 对象；全部失败抛 JSONDecodeError（doc 保留原始文本，
供上层把整段原始响应打进报错信息）。类型判断由调用方负责。
"""

import json
import re

_FENCE_RE = re.compile(r"```(?:json|JSON|js)?\s*(.*?)\s*```", re.DOTALL)
_ESCAPE = {"\n": r"\n", "\r": r"\r", "\t": r"\t", "\b": r"\b", "\f": r"\f"}


def _strip_fences(raw: str) -> str:
    m = _FENCE_RE.search(raw)
    return m.group(1) if m else raw


def _outermost_span(text: str):
    """返回最外层 JSON 值（{…} 或 […]）的 (start, end) 下标，未找到返回 None。

    逐字符扫描并跟踪字符串/转义状态，用括号配平定位，保证不会把内层的
    子数组/子对象误当成顶层结构（旧的 find/rfind 截取会踩这个坑）。
    """
    start = None
    stack = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if c == "\\":
                i += 2  # 跳过转义字符
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c in "{[":
            if start is None:
                start = i
            stack.append(c)
        elif c in "}]":
            if stack:
                stack.pop()
                if not stack:
                    return start, i
        i += 1
    return None


def _repair(text: str) -> str:
    """修复 LLM 输出中常见的 JSON 缺陷：对象/数组的尾逗号、字符串内的裸控制符。

    逐字符扫描并跟踪字符串/转义状态，只在真正危险的位置改写：
    - 字符串内：把裸控制符转成合法转义（\\n \\r \\t \\b \\f，其余 \\u00XX）；
    - 字符串外：删除 `}` / `]` 前的多余逗号。
    若输入遇到了无法归类的破坏，仍尽可能原样返回，交由上层照常报错。
    """
    out = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if c == "\\":
                out.append(c)
                if i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                i += 1
                continue
            if c == '"':
                in_string = False
                out.append(c)
                i += 1
                continue
            if ord(c) < 0x20:
                esc = _ESCAPE.get(c)
                out.append(esc if esc is not None else "\\u%04x" % ord(c))
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c in "}]":
            j = len(out) - 1
            while j >= 0 and out[j].isspace():
                j -= 1
            if j >= 0 and out[j] == ",":
                del out[j:]
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _candidates(raw: str):
    """按可解析性从优到劣产出候选文本（去重）。"""
    stem = _strip_fences(raw)
    cands = []
    for s in (raw, stem):
        if s not in cands:
            cands.append(s)
        span = _outermost_span(s)
        if span:
            frag = s[span[0]:span[1] + 1]
            if frag not in cands:
                cands.append(frag)
    return cands


def loads_coerce(raw):
    """解析 LLM 返回的 JSON，容忍围栏、夹带文字与常见缺陷。失败抛 JSONDecodeError。"""
    text = raw.strip() if isinstance(raw, str) else raw
    seen = set()
    for candidate in _candidates(text):
        for attempt in (candidate, _repair(candidate)):
            if attempt in seen:
                continue
            seen.add(attempt)
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("未能在响应中解析出 JSON", text, 0)