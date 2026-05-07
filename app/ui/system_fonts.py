"""Cross-platform font helpers for raw ``tk.*`` / ``ttk.*`` widgets.

CTk widgets carry their own platform-aware default (Roboto on
Win/Linux, SF Display on Mac) — pass ``ctk.CTkFont(size=N, ...)``
without a family and CTk picks the right one. Raw tk widgets don't
get that treatment, so we derive from Tk's own named system fonts
(``TkDefaultFont`` / ``TkFixedFont``), which Tk maps per platform:

    * Win   → Segoe UI 9 / Consolas
    * Mac   → .AppleSystemUIFont / Menlo
    * Linux → DejaVu Sans / DejaVu Sans Mono (or distro equivalent)

Three call shapes are exposed:

* ``ui_font(size, *style)`` — tuple form for ``font=(...)`` kwargs.
  Replaces the historical hardcoded ``("Segoe UI", N)`` literals.
* ``derive_ui_font(**overrides)`` — full ``tkinter.font.Font`` object
  for callers that need ``.measure(...)``, ``.metrics(...)``, or live
  reconfigure. Copies ``TkDefaultFont``.
* ``derive_mono_font(**overrides)`` — same, but copies ``TkFixedFont``
  for monospace surfaces (code views, bug-reporter trace, etc.).

The named-font lookup requires a live Tk root, so every helper here
must be called at runtime (after ``tk.Tk()`` exists) — never at
module import time.
"""

from __future__ import annotations

from tkinter.font import Font, nametofont


def ui_font(size: int, *style: str) -> tuple:
    """Return a Tk font tuple keyed to the host's default UI family.

    ``style`` accepts any number of Tk style words: ``"bold"``,
    ``"italic"``, ``"underline"``, ``"overstrike"``.

    Examples::

        ui_font(10)                       # ("Segoe UI", 10) on Win
        ui_font(14, "bold")               # ("Segoe UI", 14, "bold")
        ui_font(9, "underline")           # ("Segoe UI", 9, "underline")
        ui_font(13, "bold", "underline")  # ("Segoe UI", 13, "bold", "underline")

    Use as ``font=ui_font(N)`` anywhere a tuple was previously used.
    For callers that need a Font object instead (``.measure()``, etc.)
    use ``derive_ui_font`` below.
    """
    family = nametofont("TkDefaultFont").cget("family")
    if style:
        return (family, size, *style)
    return (family, size)


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
