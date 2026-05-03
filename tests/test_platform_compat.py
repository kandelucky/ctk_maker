"""Sanity checks for the platform_compat constants.

The module's primary purpose is to expose three booleans
(IS_MAC / IS_WINDOWS / IS_LINUX) and a handful of platform-conditional
constants. We can't verify the Mac branch on Win CI, but we can
verify (a) exactly one boolean is True, (b) the constants resolve
to the expected types, and (c) the Win branch produces the values
the rest of the codebase already relies on.
"""

from __future__ import annotations

from app.core import platform_compat as pc


def test_exactly_one_platform_flag_is_true():
    flags = (pc.IS_MAC, pc.IS_WINDOWS, pc.IS_LINUX)
    assert sum(bool(f) for f in flags) == 1


def test_modifier_constants_are_strings():
    assert isinstance(pc.MOD_KEY, str) and pc.MOD_KEY
    assert isinstance(pc.MOD_LABEL, str) and pc.MOD_LABEL
    assert isinstance(pc.MOD_LABEL_PLUS, str) and pc.MOD_LABEL_PLUS


def test_alt_state_bit_is_int():
    assert isinstance(pc.ALT_STATE_BIT, int)
    assert pc.ALT_STATE_BIT > 0


def test_windows_branch_matches_legacy_hardcoded_values():
    """The Win values must equal what the codebase has always used —
    otherwise the migration would silently regress Windows behavior.
    """
    if not pc.IS_WINDOWS:
        return
    assert pc.MOD_KEY == "Control"
    assert pc.MOD_LABEL == "Ctrl"
    assert pc.MOD_LABEL_PLUS == "Ctrl+"
    assert pc.ALT_STATE_BIT == 0x20000


def test_no_font_constants_exposed():
    """Fonts are intentionally not handled here — see module docstring.
    CTk widgets use ctk.CTkFont(); raw tk widgets derive from
    tkinter.font.nametofont("TkDefaultFont"). Adding font constants
    here would re-introduce the Windows-only bias the migration is
    meant to remove.
    """
    assert not hasattr(pc, "UI_FONT_FAMILY")
    assert not hasattr(pc, "MONO_FONT_FAMILY")
