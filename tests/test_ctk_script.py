"""Tests for the ``CTkScript`` base class — the Unity-style behavior
base users subclass. Scope is strict: a widget-attached script gets
``self.widget`` and no window; a window-attached script gets
``self.window`` and no widget. Pure-Python, no Tk. See
docs/plans/script_optimization.md (CTkScript model).
"""
from __future__ import annotations

from app.io.scripts.ctk_script import CTkScript


# -- Scope injection --------------------------------------------------

def test_widget_attach_sets_widget_only():
    w = object()
    script = CTkScript(widget=w)
    assert script.widget is w
    # Strict scope: a widget script knows nothing about the window.
    assert not hasattr(script, "window")


def test_window_attach_sets_window_only():
    win = object()
    script = CTkScript(window=win)
    assert script.window is win
    assert not hasattr(script, "widget")


def test_no_context_when_unattached():
    script = CTkScript()
    assert not hasattr(script, "widget")
    assert not hasattr(script, "window")


def test_subclass_receives_context():
    win = object()

    class LoginForm(CTkScript):
        pass

    assert LoginForm(window=win).window is win


def test_context_set_after_construction():
    # The export wires it this way: build the instance, then assign.
    w = object()
    script = CTkScript()
    script.widget = w
    assert script.widget is w


# -- Lifecycle hooks --------------------------------------------------

def test_lifecycle_hooks_are_noops():
    script = CTkScript()
    assert script.on_start() is None
    assert script.on_close() is None


def test_subclass_overrides_lifecycle():
    calls = []

    class Logic(CTkScript):
        def on_start(self):
            calls.append("start")

    Logic().on_start()
    assert calls == ["start"]


# -- Inline-readiness -------------------------------------------------

def test_no_runtime_imports():
    # The base must stay import-free so the exporter can inline it
    # verbatim into a self-contained build.
    import ast
    import inspect

    from app.io.scripts import ctk_script

    tree = ast.parse(inspect.getsource(ctk_script))
    imports = [
        n for n in tree.body
        if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    assert imports == []
