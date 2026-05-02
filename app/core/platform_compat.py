"""Platform-aware constants for cross-platform branching.

Centralises the recurring decisions — modifier keys, accelerator
labels, font fallbacks, Alt/Option modifier bit masks — that
otherwise pepper the codebase with ``if platform.system() == "Darwin":``
checks.

Use the constants here when the same decision repeats across many
call sites (modifier keys, fonts). Inline ``if IS_MAC:`` is still
fine for one-off platform-specific code paths (editor launch,
Button-2 binding, Retina DPI scaling, ``open`` vs ``open -t``).

All Mac- and Linux-specific values are SUSPECTED — none have been
reproduced on real hardware. See GitHub issue #5
(macOS support — known incompatibilities) for the running list.

Naming note
-----------
The module is named ``platform_compat`` (not ``platform``) so it
never shadows the stdlib ``platform`` module that callers may also
need to import.
"""

from __future__ import annotations

import platform as _platform

_SYSTEM = _platform.system()

IS_MAC = _SYSTEM == "Darwin"
IS_WINDOWS = _SYSTEM == "Windows"
IS_LINUX = _SYSTEM == "Linux"

# Modifier key for Tk bind strings.
# Use as: widget.bind(f"<{MOD_KEY}-s>", handler)
# Win/Linux → "Control"; Mac → "Command" (Tk-aqua maps this to ⌘).
MOD_KEY = "Command" if IS_MAC else "Control"

# Standalone modifier label for UI text (no trailing separator).
# Example: f"{MOD_LABEL} key" → "Ctrl key" on Win/Linux, "⌘ key" on Mac.
MOD_LABEL = "⌘" if IS_MAC else "Ctrl"

# Accelerator label for menu items / shortcut hints.
# Concatenate directly with the next char. Mac convention is no
# separator (⌘S), Win/Linux is plus (Ctrl+S).
# Example: f"{MOD_LABEL_PLUS}S" → "Ctrl+S" / "⌘S".
MOD_LABEL_PLUS = "⌘" if IS_MAC else "Ctrl+"

# Alt / Option bit in Tk's ``event.state`` bitmask.
# Used by snap-bypass during drag and "fine mode" in numeric drag-scrub.
# UNVERIFIED on Mac — Tk-aqua docs put the Option bit at 0x10, but
# this hasn't been confirmed on hardware. See GitHub issue #5.
ALT_STATE_BIT = 0x10 if IS_MAC else 0x20000

# Font handling note
# ------------------
# Intentionally no UI / mono font constants here. The codebase used
# to hardcode ``("Segoe UI", N)`` / ``("Consolas", N)`` font tuples,
# which forces a Windows-only family on every platform and defeats
# both Tk's named-font system and CTk's own platform-aware default.
# The migration target is:
#
#   * CTk widgets → ``ctk.CTkFont(size=N, weight=...)`` so CTk's
#     theme family (Roboto on Win/Linux, SF Display on Mac) wins
#   * raw ``tk.*`` / ``ttk.*`` widgets → derive from Tk named fonts:
#     ``tkinter.font.nametofont("TkDefaultFont").copy().configure(size=N)``
#     (use ``"TkFixedFont"`` for monospace surfaces)
#
# Both strategies adapt to the host platform automatically — no
# ``IS_MAC`` branching needed for fonts.
