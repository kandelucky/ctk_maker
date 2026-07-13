"""Row assembly for the Script Variables panel group — build_variable_rows.
Pure-Python, no Tk. See docs/plans/archive/script_variable_binding.md.
"""
from __future__ import annotations

from app.core.variables import VariableEntry
from app.io.scripts import build_variable_rows

SCRIPT = (
    "import tkinter as tk\n"
    "from ctkmaker import CTkScript\n"
    "class Counter(CTkScript):\n"
    "    score: tk.IntVar\n"
    "    title: tk.StringVar\n"
)


def _write(tmp_path, name, body):
    (tmp_path / name).write_text(body, encoding="utf-8")


def test_rows_pair_fields_with_binding_and_eligible(tmp_path):
    _write(tmp_path, "counter.py", SCRIPT)
    g_int = VariableEntry(name="hp", type="int", scope="global")
    g_col = VariableEntry(name="accent", type="color", scope="global")
    l_str = VariableEntry(name="label", type="str", scope="local")
    components = [
        {"script": "counter.py", "class": "Counter",
         "var_bindings": {"score": g_int.id}},
    ]
    rows = build_variable_rows(components, tmp_path, [g_int, g_col], [l_str])
    assert len(rows) == 2

    score, title = rows
    assert (score["field"], score["var_type"]) == ("score", "int")
    assert score["bound_id"] == g_int.id
    assert [v.name for v in score["eligible"]] == ["hp"]          # int only

    assert (title["field"], title["var_type"]) == ("title", "str")
    assert title["bound_id"] is None
    # str field → str + color (A1), globals before locals
    assert [v.name for v in title["eligible"]] == ["accent", "label"]


def test_component_missing_class_or_script_skipped(tmp_path):
    _write(tmp_path, "counter.py", SCRIPT)
    components = [
        {"script": "counter.py"},   # no class
        {"class": "Counter"},        # no script
    ]
    assert build_variable_rows(components, tmp_path, [], []) == []


def test_script_with_no_exposed_fields(tmp_path):
    _write(
        tmp_path, "plain.py",
        "from ctkmaker import CTkScript\nclass Plain(CTkScript):\n    pass\n",
    )
    components = [{"script": "plain.py", "class": "Plain"}]
    assert build_variable_rows(components, tmp_path, [], []) == []


def test_no_scripts_dir_yields_no_rows():
    components = [{"script": "counter.py", "class": "Counter"}]
    assert build_variable_rows(components, None, [], []) == []
