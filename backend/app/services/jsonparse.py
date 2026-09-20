"""健壮解析 LLM 返回的 JSON。

模型虽被要求"严格只输出一个 JSON 对象/数组"，但实际常把内容包进 ```json 代码围栏，
或在前后夹带说明文字（如"好的，伏笔种子如下："）。直接用 json.loads 解析原始文本会
抛 JSONDecodeError，导致前置构建中断。这里按优先级依次尝试：

1. 原始文本整体解析；
2. 剥离 markdown 代码围栏后解析（ ```json ... ``` / ``` ... ``` ）；
3. 截取第一个 { 或 [ 到最后一个 } 或 ] 之间的片段再解析。

任一成功即返回对应 Python 对象；全部失败抛 JSONDecodeError（doc 保留原始文本，
供上层把整段原始响应打进报错信息）。类型判断由调用方负责。
"""

import json
import re

_FENCE_RE = re.compile(r"```(?:json|JSON|js)?\s*(.*?)\s*```", re.DOTALL)
_OPEN = ("{", "[")
_CLOSE = ("}", "]")


def _candidates(raw: str):
    stem = _strip_fences(raw)
    yield raw
    if stem != raw:
        yield stem
    for open_c, close_c in zip(_OPEN, _CLOSE):
        start = raw.find(open_c)
        end = raw.rfind(close_c)
        if start != -1 and end > start:
            yield raw[start:end + 1]


def _strip_fences(raw: str) -> str:
    m = _FENCE_RE.search(raw)
    return m.group(1) if m else raw


def loads_coerce(raw: str):
    """解析 LLM 返回的 JSON，容忍 markdown 围栏与上下文文字。失败抛 JSONDecodeError。"""
    text = raw.strip() if isinstance(raw, str) else raw
    for candidate in _candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise json.JSONDecodeError("未能在响应中解析出 JSON", text, 0)