"""Guards for the DPI-scaled raw-tk layer (``app.ui.stk``).

Two things must not regress:

1. The scaling math — pixel dims / paddings / tuple-font sizes scale by
   the widget factor, character ``width`` does **not** (that is the one
   subtlety that makes ``stk`` correct where a naive "scale every
   ``width``" shim would break Label/Button/Entry).
2. The migrated dialogs must keep using ``stk.*`` for their visual
   widgets — a stray ``tk.Frame(`` / ``tk.Label(`` / ``tk.Entry(``
   silently reintroduces the un-scaled content this layer exists to fix.

Both checks are display-free (no Tk root), so they run anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import app.ui.stk as stk

REPO_ROOT = Path(__file__).resolve().parent.parent

# Dialogs migrated onto stk. A bare tk.Frame/Label/Entry instantiation
# here means someone reverted the DPI fix — see docs/DEV_NOTES.md.
MIGRATED_MODULES = (
    "settings_dialog",
    "font_picker_dialog",
    "lucide_icon_picker_dialog",
    "variables_window",
    "color_palette_window",
    "object_tree_window",
    "image_picker_dialog",
    "quick_export_dialog",
    "project_window",
    "console_window",
    "export_dialog",
    "save_as_dialog",
    "widget_picker_dialog",
)

# Bare ``tk.Frame(`` etc. — the leading (?<![A-Za-z]) rejects the ``tk``
# inside ``stk.Frame(``.
_BARE_TK = re.compile(r"(?<![A-Za-z])tk\.(Frame|Label|Entry)\(")


# ----------------------------------------------------------------------
# Scaling math

def test_pixel_value_scales():
    assert stk._scale_num(170, 1.5) == 255
    assert stk._scale_num(14, 1.5) == 21


def test_non_numeric_passthrough():
    assert stk._scale_num("center", 1.5) == "center"
    assert stk._scale_num(None, 1.5) is None


def test_pad_tuple_scales_each_element():
    assert stk._scale_pad((18, 6), 1.5) == (27, 9)
    assert stk._scale_pad(8, 1.5) == 12


def test_tuple_font_size_scales():
    assert stk._scale_font(("Segoe UI", 11), 1.5) == ("Segoe UI", 16)
    assert stk._scale_font(("Segoe UI", 11, "bold"), 1.5) == (
        "Segoe UI", 16, "bold",
    )


def test_non_tuple_font_untouched():
    # CTkFont-style / bare family string / sizeless tuple carry no
    # scalable numeric size — must pass through unchanged.
    assert stk._scale_font("Arial", 1.5) == "Arial"
    assert stk._scale_font(("Arial",), 1.5) == ("Arial",)


def test_identity_at_scale_one():
    assert stk._scale_num(170, 1.0) == 170
    assert stk._scale_font(("Segoe UI", 11), 1.0) == ("Segoe UI", 11)


# ----------------------------------------------------------------------
# The character-width rule: pixel-size scaling only on Frame/Canvas.

def test_frame_scales_pixel_dimensions():
    assert stk.Frame._SIZE_PX == ("width", "height")
    assert stk.Canvas._SIZE_PX == ("width", "height")


def test_text_widgets_never_scale_char_width():
    # width on these counts characters, not pixels — scaling it would
    # shrink/grow the control wrongly. It must stay out of _SIZE_PX.
    for cls in (stk.Label, stk.Button, stk.Entry, stk.Checkbutton,
                stk.Radiobutton, stk.Message):
        assert "width" not in cls._SIZE_PX
        assert "height" not in cls._SIZE_PX


# ----------------------------------------------------------------------
# Migration guard

def test_migrated_dialogs_use_stk_not_bare_tk():
    offenders = {}
    for mod in MIGRATED_MODULES:
        src = (REPO_ROOT / "app" / "ui" / f"{mod}.py").read_text(
            encoding="utf-8",
        )
        hits = _BARE_TK.findall(src)
        if hits:
            offenders[mod] = hits
    assert not offenders, (
        "Bare tk.Frame/Label/Entry re-introduced in migrated dialogs — "
        "use app.ui.stk instead (see docs/DEV_NOTES.md): "
        f"{offenders}"
    )
