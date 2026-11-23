"""Word-level diff between original and corrected text, rendered as Qt rich text."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_TOKEN_RE = re.compile(r"\s+|\w+(?:['’]\w+)*|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class DiffOp:
    tag: str  # "equal" | "delete" | "insert" | "replace"
    a: str
    b: str


@dataclass(frozen=True)
class DiffColors:
    ins_bg: str = "#c9f2e2"
    ins_fg: str = "#0b5d46"
    del_bg: str = "#fbd5d8"
    del_fg: str = "#9b1c28"


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def compute_diff(original: str, corrected: str) -> list[DiffOp]:
    ta, tb = tokenize(original), tokenize(corrected)
    sm = SequenceMatcher(None, ta, tb, autojunk=False)
    ops: list[DiffOp] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        ops.append(DiffOp(tag, "".join(ta[i1:i2]), "".join(tb[j1:j2])))
    return _merge_small_gaps(ops)


def _merge_small_gaps(ops: list[DiffOp]) -> list[DiffOp]:
    """Join changes separated only by a single space so 'a apple'->'an Apple' reads as one edit."""
    merged: list[DiffOp] = []
    i = 0
    while i < len(ops):
        op = ops[i]
        if (
            merged and op.tag == "equal" and op.a.isspace() and "\n" not in op.a
            and merged[-1].tag != "equal" and i + 1 < len(ops) and ops[i + 1].tag != "equal"
        ):
            prev, nxt = merged.pop(), ops[i + 1]
            merged.append(DiffOp("replace", prev.a + op.a + nxt.a, prev.b + op.b + nxt.b))
            i += 2
            continue
        if merged and op.tag != "equal" and merged[-1].tag != "equal":
            prev = merged.pop()
            merged.append(DiffOp("replace", prev.a + op.a, prev.b + op.b))
        else:
            merged.append(op)
        i += 1
    return merged


def change_count(ops: list[DiffOp]) -> int:
    return sum(1 for op in ops if op.tag != "equal" and (op.a.strip() or op.b.strip()))


def _esc(text: str) -> str:
    return html.escape(text).replace("\r\n", "\n").replace("\n", "<br>")


def render_side(ops: list[DiffOp], side: str, colors: DiffColors | None = None) -> str:
    """Render one pane: side='original' highlights removals, 'corrected' highlights additions."""
    c = colors or DiffColors()
    out: list[str] = []
    for op in ops:
        if op.tag == "equal":
            out.append(_esc(op.a if side == "original" else op.b))
            continue
        if side == "original" and op.a:
            out.append(
                f'<span style="background-color:{c.del_bg}; color:{c.del_fg}; '
                f'text-decoration:line-through;">{_esc(op.a)}</span>'
            )
        elif side == "corrected" and op.b:
            out.append(
                f'<span style="background-color:{c.ins_bg}; color:{c.ins_fg}; font-weight:600;">'
                f"{_esc(op.b)}</span>"
            )
    return '<div style="white-space:pre-wrap;">' + "".join(out) + "</div>"


def render_inline(ops: list[DiffOp], colors: DiffColors | None = None) -> str:
    """Single-pane view: removed text struck through followed by inserted text."""
    c = colors or DiffColors()
    out: list[str] = []
    for op in ops:
        if op.tag == "equal":
            out.append(_esc(op.b))
            continue
        if op.a:
            out.append(
                f'<span style="background-color:{c.del_bg}; color:{c.del_fg}; '
                f'text-decoration:line-through;">{_esc(op.a)}</span>'
            )
            if op.b:
                out.append(" ")  # thin visual gap between removed and inserted text (display only)
        if op.b:
            out.append(
                f'<span style="background-color:{c.ins_bg}; color:{c.ins_fg}; font-weight:600;">{_esc(op.b)}</span>'
            )
    return '<div style="white-space:pre-wrap;">' + "".join(out) + "</div>"


def plain_html(text: str) -> str:
    return '<div style="white-space:pre-wrap;">' + _esc(text) + "</div>"
