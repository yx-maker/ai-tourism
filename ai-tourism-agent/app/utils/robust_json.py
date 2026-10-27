"""大模型结构化输出的多层容错解析器（对标 TripStar 的容错 JSON 解析）。

设计目标
--------
大语言模型在生成 JSON 时常见问题：包裹 Markdown 代码围栏、前后夹杂解释性文字、
使用中文引号或单引号、输出被 max_tokens 截断导致括号不闭合。本模块用**逐层降级**
策略把这些情况逐个兜住，并把命中的层级编号返回，便于统计各层命中率（论文实验数据）。

层级（layer）
-------------
1. 直接解析
2. 剥离 Markdown 代码围栏 / 前后杂质
3. 提取最外层 {...} 或 [...]
4. 引号修复（中文引号、单引号、未转义引号）
5. 截断修复（补齐缺失的括号、去除尾逗号）
6. LLM 修复兜底（需调用方传入 llm_fix 回调，可选）

用法
----
    from app.utils import parse_llm_json

    res = parse_llm_json(llm_text)          # 失败抛 JSONDecodeError
    print(res.data, res.layer)              # 解析结果 + 命中层级

    res = parse_llm_json(llm_text, llm_fix=lambda raw: call_llm(raw))
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional


class RobustJsonError(ValueError):
    """所有层级都失败时抛出。"""


@dataclass
class ParseResult:
    """解析结果。

    Attributes:
        data: 解析出的对象（dict / list）。
        layer: 命中的层级编号（1~6），用于统计各层命中率。
        repaired: 是否经过了修复（layer >= 3）。
    """

    data: Any
    layer: int
    repaired: bool = False


_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)
_OBJECT_RE = re.compile(r"\{.*\}", re.S)
_ARRAY_RE = re.compile(r"\[.*\]", re.S)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _try_json(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _strip_fence(text: str) -> str:
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _extract_outer(text: str) -> Optional[str]:
    """取最外层对象或数组（谁先出现取谁）。"""
    o = _OBJECT_RE.search(text)
    a = _ARRAY_RE.search(text)
    if o and a:
        return o.group(0) if o.start() < a.start() else a.group(0)
    if o:
        return o.group(0)
    if a:
        return a.group(0)
    return None


def _repair_quotes(text: str) -> str:
    """把中文引号/单引号规整为 JSON 双引号，并尽量修复裸引号。"""
    t = text.replace("“", '"').replace("”", '"')
    t = t.replace("‘", "'").replace("’", "'")
    # 仅在 key/value 位置把单引号替换为双引号（保守做法：全部替换）
    t = t.replace("'", '"')
    # 修复形如 {"a": 值} 中裸露的、未加引号的 key
    t = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', t)
    return t


def _repair_truncation(text: str) -> str:
    """补齐缺失的右括号 / 去掉尾逗号，修复被截断的 JSON。"""
    t = _TRAILING_COMMA_RE.sub(r"\1", text.strip())
    stack = []
    in_str = False
    esc = False
    for ch in t:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
    if in_str:
        t += '"'
    while stack:
        t += "}" if stack.pop() == "{" else "]"
    t = _TRAILING_COMMA_RE.sub(r"\1", t)
    return t


def parse_llm_json(
    text: str,
    llm_fix: Optional[Callable[[str], str]] = None,
) -> ParseResult:
    """多层容错解析大模型返回的 JSON 文本。

    Args:
        text: 大模型原始输出。
        llm_fix: 可选的 LLM 修复回调，接收原始文本、返回修复后的 JSON 字符串。

    Returns:
        ParseResult(data, layer, repaired)。

    Raises:
        RobustJsonError: 所有层级均失败。
    """
    if not text or not text.strip():
        raise RobustJsonError("输入为空")

    # layer 1: 直接解析
    obj = _try_json(text)
    if obj is not None:
        return ParseResult(obj, layer=1)

    # layer 2: 剥离代码围栏 / 前后杂质
    stripped = _strip_fence(text)
    obj = _try_json(stripped)
    if obj is not None:
        return ParseResult(obj, layer=2)

    # layer 3: 提取最外层对象/数组
    outer = _extract_outer(stripped) or _extract_outer(text)
    if outer:
        obj = _try_json(outer)
        if obj is not None:
            return ParseResult(obj, layer=3, repaired=True)
    else:
        outer = stripped

    # layer 4: 引号修复
    quoted = _repair_quotes(outer)
    obj = _try_json(quoted)
    if obj is not None:
        return ParseResult(obj, layer=4, repaired=True)

    # layer 5: 截断修复
    fixed = _repair_truncation(quoted)
    obj = _try_json(fixed)
    if obj is not None:
        return ParseResult(obj, layer=5, repaired=True)

    # layer 6: LLM 修复兜底
    if llm_fix is not None:
        try:
            repaired_text = llm_fix(text)
            obj = _try_json(_strip_fence(repaired_text))
            if obj is None:
                obj = _try_json(_repair_truncation(_repair_quotes(repaired_text)))
            if obj is not None:
                return ParseResult(obj, layer=6, repaired=True)
        except Exception:
            pass

    raise RobustJsonError("所有容错层级均解析失败")


if __name__ == "__main__":  # pragma: no cover - 手工冒烟
    samples = [
        ('{"a": 1}', 1),
        ('```json\n{"a": 1}\n```', 2),
        ('好的，结果如下：{"a": 1} 以上。', 3),
        ("{'a': 1}", 4),
        ('{"a": 1, "b": [1, 2', 5),
    ]
    for s, expect in samples:
        r = parse_llm_json(s)
        flag = "OK " if r.layer == expect else "!! "
        print(f"{flag}layer={r.layer} expect={expect} data={r.data}")
