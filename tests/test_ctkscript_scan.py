"""CTkScript model — discovery of attachable script classes.

``parse_ctkscript_classes`` finds CTkScript subclasses in one file;
``find_attachable_scripts`` scans a ``scripts/`` folder; ``user_scripts_dir``
locates that folder at the project root. Pure-Python, no Tk.
See docs/plans/script_optimization.md.
"""
from __future__ import annotations

from pathlib import Path

from app.core.script_paths import user_scripts_dir
from app.io.scripts import (
    create_user_script,
    find_attachable_scripts,
    parse_ctkscript_classes,
    parse_exposed_variables,
)


# -- create_user_script -----------------------------------------------

def test_create_user_script_writes_skeleton(tmp_path):
    rel, cls = create_user_script(tmp_path, "ClickCounter")
    assert (rel, cls) == ("click_counter.py", "ClickCounter")
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert "from ctkmaker import CTkScript" in text
    assert "class ClickCounter(CTkScript):" in text
    # Round-trips through the scanner.
    assert find_attachable_scripts(tmp_path) == [("click_counter.py", "ClickCounter")]


def test_create_user_script_auto_suffixes(tmp_path):
    create_user_script(tmp_path, "Foo")
    rel2, _ = create_user_script(tmp_path, "Foo")
    assert rel2 == "foo_2.py"


def test_create_user_script_rejects_invalid_name(tmp_path):
    assert create_user_script(tmp_path, "9bad") is None
    assert create_user_script(tmp_path, "has space") is None
    assert create_user_script(tmp_path, "") is None


def test_create_user_script_unsaved_returns_none():
    assert create_user_script(None, "Foo") is None


# -- parse_ctkscript_classes ------------------------------------------

def test_finds_ctkscript_subclass(tmp_path):
    f = tmp_path / "counter.py"
    f.write_text(
        "from ctkmaker import CTkScript\n\n"
        "class ClickCounter(CTkScript):\n    pass\n",
        encoding="utf-8",
    )
    assert parse_ctkscript_classes(f) == ["ClickCounter"]


def test_finds_qualified_base(tmp_path):
    f = tmp_path / "x.py"
    f.write_text(
        "import ctkmaker\n\n"
        "class A(ctkmaker.CTkScript):\n    pass\n",
        encoding="utf-8",
    )
    assert parse_ctkscript_classes(f) == ["A"]


def test_ignores_non_ctkscript_classes(tmp_path):
    f = tmp_path / "x.py"
    f.write_text(
        "class Plain:\n    pass\n"
        "class Helper(object):\n    pass\n",
        encoding="utf-8",
    )
    assert parse_ctkscript_classes(f) == []


def test_multiple_classes_in_one_file(tmp_path):
    f = tmp_path / "x.py"
    f.write_text(
        "from ctkmaker import CTkScript\n"
        "class A(CTkScript): pass\n"
        "class B(CTkScript): pass\n"
        "class C: pass\n",
        encoding="utf-8",
    )
    assert parse_ctkscript_classes(f) == ["A", "B"]


def test_syntax_error_returns_empty(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("class A(CTkScript:\n", encoding="utf-8")
    assert parse_ctkscript_classes(f) == []


def test_missing_file_returns_empty(tmp_path):
    assert parse_ctkscript_classes(tmp_path / "nope.py") == []


# -- parse_exposed_variables ------------------------------------------

def test_exposed_vars_bare_and_dotted(tmp_path):
    f = tmp_path / "x.py"
    f.write_text(
        "import tkinter as tk\n"
        "from tkinter import IntVar\n"
        "from ctkmaker import CTkScript\n"
        "class A(CTkScript):\n"
        "    score: tk.IntVar\n"
        "    title: tk.StringVar\n"
        "    ratio: tk.DoubleVar\n"
        "    flag: tk.BooleanVar\n"
        "    bare: IntVar\n",
        encoding="utf-8",
    )
    assert parse_exposed_variables(f, "A") == [
        ("score", "int"),
        ("title", "str"),
        ("ratio", "float"),
        ("flag", "bool"),
        ("bare", "int"),
    ]


def test_exposed_vars_skips_annotation_with_value(tmp_path):
    # A value means script-owned state, not an injected field.
    f = tmp_path / "x.py"
    f.write_text(
        "import tkinter as tk\n"
        "from ctkmaker import CTkScript\n"
        "class A(CTkScript):\n"
        "    injected: tk.StringVar\n"
        "    own: tk.StringVar = tk.StringVar()\n",
        encoding="utf-8",
    )
    assert parse_exposed_variables(f, "A") == [("injected", "str")]


def test_exposed_vars_ignores_non_var_annotations(tmp_path):
    f = tmp_path / "x.py"
    f.write_text(
        "from ctkmaker import CTkScript\n"
        "class A(CTkScript):\n"
        "    count: int\n"
        "    label: str\n"
        "    misc: object\n",
        encoding="utf-8",
    )
    assert parse_exposed_variables(f, "A") == []


def test_exposed_vars_only_named_class_no_methods(tmp_path):
    f = tmp_path / "x.py"
    f.write_text(
        "import tkinter as tk\n"
        "from ctkmaker import CTkScript\n"
        "class A(CTkScript):\n"
        "    score: tk.IntVar\n"
        "    def on_start(self): pass\n"
        "class B(CTkScript):\n"
        "    other: tk.StringVar\n",
        encoding="utf-8",
    )
    assert parse_exposed_variables(f, "A") == [("score", "int")]


def test_exposed_vars_missing_and_broken(tmp_path):
    assert parse_exposed_variables(tmp_path / "nope.py", "A") == []
    bad = tmp_path / "bad.py"
    bad.write_text("class A(CTkScript:\n", encoding="utf-8")
    assert parse_exposed_variables(bad, "A") == []


# -- find_attachable_scripts ------------------------------------------

def test_scan_folder(tmp_path):
    (tmp_path / "counter.py").write_text(
        "from ctkmaker import CTkScript\nclass ClickCounter(CTkScript): pass\n",
        encoding="utf-8",
    )
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "auth.py").write_text(
        "from ctkmaker import CTkScript\nclass Auth(CTkScript): pass\n",
        encoding="utf-8",
    )
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "counter.cpython-314.pyc").write_bytes(b"\x00")

    assert find_attachable_scripts(tmp_path) == [
        ("counter.py", "ClickCounter"),
        ("sub/auth.py", "Auth"),
    ]


def test_scan_missing_folder(tmp_path):
    assert find_attachable_scripts(tmp_path / "nope") == []
    assert find_attachable_scripts(None) == []


# -- user_scripts_dir -------------------------------------------------

def test_user_scripts_dir_at_project_root(tmp_path):
    (tmp_path / "project.json").write_text("{}", encoding="utf-8")
    pages = tmp_path / "assets" / "pages"
    pages.mkdir(parents=True)
    page = pages / "main.ctkproj"
    page.write_text("{}", encoding="utf-8")
    assert user_scripts_dir(page) == tmp_path / "scripts"


def test_user_scripts_dir_unsaved():
    assert user_scripts_dir(None) is None
