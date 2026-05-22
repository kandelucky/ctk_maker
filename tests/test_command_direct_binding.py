"""Phase 1 (cont.) — direct script binding for command-style widgets.

Argless commands (Button, Switch, CheckBox, RadioButton) call the
user's function as ``func(window)``; value-commands (Slider, ComboBox,
OptionMenu, SegmentedButton) as ``func(window, value)``. The Function
picker's signature filter mirrors that. Pure-Python, no Tk.
See docs/plans/script_optimization.md.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.io import code_exporter
from app.io.code_exporter import _emit_handler_lines
from app.io.scripts import parse_module_functions


def _node(widget_type: str, method: str = "on_it"):
    return SimpleNamespace(
        widget_type=widget_type,
        name="w",
        id="w1",
        handlers={
            "command": [
                {"kind": "library_call", "script": "helpers.py", "method": method},
            ],
        },
    )


# --------------------------------------------------------------------
# Export emission

def test_button_command_passes_window_only(monkeypatch):
    monkeypatch.setattr(code_exporter, "_EXPORT_PROJECT", None)
    command_kwarg, post_lines = _emit_handler_lines(
        _node("CTkButton", "on_press"), "self.btn",
    )
    assert post_lines == []
    assert command_kwarg == (
        "command", "lambda: (helpers.on_press(self))",
    )


def test_slider_command_passes_window_and_value(monkeypatch):
    monkeypatch.setattr(code_exporter, "_EXPORT_PROJECT", None)
    command_kwarg, post_lines = _emit_handler_lines(
        _node("CTkSlider", "on_change"), "self.sld",
    )
    assert post_lines == []
    assert command_kwarg == (
        "command", "lambda v: (helpers.on_change(self, v))",
    )


def test_combobox_command_passes_window_and_value(monkeypatch):
    monkeypatch.setattr(code_exporter, "_EXPORT_PROJECT", None)
    command_kwarg, _ = _emit_handler_lines(
        _node("CTkComboBox", "on_select"), "self.cb",
    )
    assert command_kwarg == (
        "command", "lambda v: (helpers.on_select(self, v))",
    )


def test_page_method_command_unchanged(monkeypatch):
    # Legacy behavior-class path stays byte-identical: a single page
    # method exports as a bare reference, no lambda, no window prefix.
    monkeypatch.setattr(code_exporter, "_EXPORT_PROJECT", None)
    node = SimpleNamespace(
        widget_type="CTkButton", name="b", id="b1",
        handlers={"command": ["on_btn_click"]},
    )
    command_kwarg, _ = _emit_handler_lines(node, "self.btn")
    assert command_kwarg == ("command", "self._behavior.on_btn_click")


# --------------------------------------------------------------------
# Picker signature filter

def test_command_plain_filter_requires_window(tmp_path):
    script = tmp_path / "helpers.py"
    script.write_text(
        "def win(window): ...\n"
        "def win_default(window, flag=False): ...\n"
        "def argless(): ...\n"
        "def win_value(window, value): ...\n",
        encoding="utf-8",
    )
    plain = parse_module_functions(script, "command", command_value=False)
    assert "win" in plain
    assert "win_default" in plain
    assert "argless" not in plain      # window would be dropped
    assert "win_value" not in plain    # 2 required, only 1 passed


def test_command_value_filter_requires_window_and_value(tmp_path):
    script = tmp_path / "helpers.py"
    script.write_text(
        "def win(window): ...\n"
        "def win_value(window, value): ...\n"
        "def win_value_default(window, value=0): ...\n",
        encoding="utf-8",
    )
    value = parse_module_functions(script, "command", command_value=True)
    assert "win_value" in value
    assert "win_value_default" in value
    assert "win" not in value          # value would be dropped
