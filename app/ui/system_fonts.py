"""Cross-platform font helpers for raw ``tk.*`` / ``ttk.*`` widgets.

CTk widgets carry their own platform-aware default (Roboto on
Win/Linux, SF Display on Mac) — pass ``ctk.CTkFont(size=N, ...)``
without a family and CTk picks the right one. Raw tk widgets don't
get that treatment, so we derive from Tk's own named system fonts
(``TkDefaultFont`` / ``TkFixedFont``), which Tk maps per platform:

    * Win   → Segoe UI 9 / Consolas
    * Mac   → .AppleSystemUIFont / Menlo
    * Linux → DejaVu Sans / DejaVu Sans Mono (or distro equivalent)

Call these helpers anywhere a raw tk widget needs a font with a
custom size or style (``tk.Menu``, ``tk.Label``, ``ttk.Style``,
canvas text, etc.).

The named-font lookup requires a live Tk root, so these functions
must be called at runtime (after ``tk.Tk()`` exists) — never at
module import time.
"""

from __future__ import annotations

from tkinter.font import Font, nametofont


def derive_ui_font(**overrides) -> Font:
    """Return a Font derived from ``TkDefaultFont`` with overrides.

    ``overrides`` accepts any kwarg that ``tkinter.font.Font.configure``
    accepts: ``size``, ``weight``, ``slant``, ``underline``,
    ``overstrike``. Pass nothing for a plain platform-default font.
    """
    f = nametofont("TkDefaultFont").copy()
    if overrides:
        f.configure(**overrides)
    return f


def derive_mono_font(**overrides) -> Font:
    """Return a Font derived from ``TkFixedFont`` with overrides.

    Use for code-display surfaces (export header, bug-reporter trace,
    ``ttk.Treeview`` cells showing identifiers, etc.) where a
    monospace family is wanted regardless of platform.
    """
    f = nametofont("TkFixedFont").copy()
    if overrides:
        f.configure(**overrides)
    return f
