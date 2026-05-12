"""Shared AST + source helpers used across the scripts package."""

from __future__ import annotations

import ast
from pathlib import Path


def _read_source(file_path: str | Path) -> str | None:
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return None


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    for top in tree.body:
        if isinstance(top, ast.ClassDef) and top.name == class_name:
            return top
    return None


def _detect_body_indent(
    cls: ast.ClassDef, lines: list[str],
) -> str:
    """Use the first body statement's leading whitespace as our indent.
    Empty / pass-only classes fall back to four spaces — Python's
    PEP 8 default and what the skeleton template emits.
    """
    if not cls.body:
        return "    "
    first = cls.body[0]
    line_idx = first.lineno - 1
    if line_idx < 0 or line_idx >= len(lines):
        return "    "
    raw = lines[line_idx]
    stripped = raw.lstrip()
    return raw[: len(raw) - len(stripped)] or "    "
