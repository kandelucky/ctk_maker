"""Phase 1 of the script-model replacement — direct script binding.

A label's bind event must call the user's own function with the
``(window, event)`` calling convention, and the Function picker must
only offer functions whose signature matches. Covers:

- ``_format_library_call`` injecting the ``window`` + ``event`` prefix
- ``_emit_handler_lines`` emitting the bind line for a label
- ``parse_module_functions`` signature filter for bind vs command

Pure-Python, no Tk. See docs/plans/script_optimization.md.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.io import code_exporter
from app.io.code_exporter import _emit_handler_lines, _format_library_call
from app.io.scripts import parse_module_functions


# --------------------------------------------------------------------
# _format_library_call — window/event prefix injection

def test_library_call_prefix_injects_window_and_event():
    entry = {"script": "helpers.py", "method": "on_click"}
    assert (
        _format_library_call(entry, ["self", "e"])
        == "helpers.on_click(self, e)"
    )


def test_library_call_no_prefix_stays_bare():
    # Command-style path (unchanged in Phase 1) passes no prefix.
    entry = {"script": "helpers.py", "method": "on_press"}
    assert _format_library_call(entry) == "helpers.on_press()"


def test_library_call_uses_module_basename():
    entry = {"script": "sub/auth.py", "method": "login"}
    assert (
        _format_library_call(entry, ["self", "e"])
        == "auth.login(self, e)"
    )


# --------------------------------------------------------------------
# _emit_handler_lines — label bind emission

def test_emit_label_bind_passes_window_and_event(monkeypatch):
    # No export project → handler filter trusts the model verbatim.
    monkeypatch.setattr(code_exporter, "_EXPORT_PROJECT", None)
    node = SimpleNamespace(
        widget_type="CTkLabel",
        name="lbl",
        id="w1",
        handlers={
            "bind:<Button-1>": [
                {
                    "kind": "library_call",
                    "script": "helpers.py",
                    "method": "on_click",
                },
            ],
        },
    )
    command_kwarg, post_lines = _emit_handler_lines(node, "self.lbl")
    assert command_kwarg is None  # labels have no command kwarg
    assert post_lines == [
        'self.lbl.bind("<Button-1>", '
        'lambda e: helpers.on_click(self, e), add="+")',
    ]


# --------------------------------------------------------------------
# parse_module_functions — bind requires (window, event)

def test_bind_filter_requires_two_positional(tmp_path):
    script = tmp_path / "helpers.py"
    script.write_text(
        "def two(window, event): ...\n"
        "def two_default(window, event=None): ...\n"
        "def one(event): ...\n"
        "def zero(): ...\n"
        "def varargs(*a): ...\n"
        "def _private(window, event): ...\n",
        encoding="utf-8",
    )
    bind_fns = parse_module_functions(script, "bind")
    assert "two" in bind_fns
    assert "two_default" in bind_fns
    assert "varargs" in bind_fns          # *args can absorb (window, event)
    assert "one" not in bind_fns          # only 1 positional — event dropped
    assert "zero" not in bind_fns
    assert "_private" not in bind_fns     # leading underscore
    # command-style filtering lives in test_command_direct_binding.py
