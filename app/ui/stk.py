"""DPI-scaled drop-in replacements for raw ``tkinter`` widgets.

Raw ``tk`` widgets do not participate in CustomTkinter's DPI scaling:
a ``tk.Frame(width=170)`` is 170 *physical* pixels regardless of the
monitor's DPI, and a tuple font such as ``ui_font(11)`` is rendered at
Tk's 96-DPI baseline. On a 150 % display that leaves raw-tk content
under-sized inside a correctly-scaled ``CTkToplevel`` frame — cramped
controls, tiny text, dead margins.

This module fixes that centrally. Import it in place of ``tkinter``
for the *visual* widgets in a dialog::

    import app.ui.stk as stk
    ...
    row = stk.Frame(parent, width=170, padx=14)
    stk.Label(row, text="Editor:", font=ui_font(11)).pack(padx=(0, 8))

and every pixel dimension, padding and tuple-font size is multiplied
by the widget's CTk *widget-scaling* factor at build time, so raw-tk
content ends up the same physical size as neighbouring CTk widgets.
Future UI stays correct by default — use ``stk.*`` and never think
about DPI again.

What gets scaled
----------------
* Pixel geometry options present in the call: ``width``/``height``
  **only on Frame/Canvas** (on Label/Button/Entry ``width`` is a
  *character* count and must not be touched — it already grows with
  the scaled font).
* ``padx`` / ``pady`` / ``wraplength`` / ``bd`` / ``borderwidth`` /
  ``highlightthickness`` — pixel options, scaled wherever present.
* ``font`` — only tuple fonts ``(family, size, ...)``; the size is
  scaled. ``CTkFont`` / string / ``tkfont.Font`` values are left
  untouched (a ``CTkFont`` scales itself; a bare family string has no
  size to scale).
* Geometry-manager padding — ``pack`` / ``grid`` / ``place`` are
  wrapped so their ``padx`` / ``pady`` / ``ipadx`` / ``ipady`` (which
  accept 2-tuples) are scaled too.

Post-construction ``configure`` / ``config`` calls are scaled the same
way, so ``widget.configure(padx=8)`` later stays consistent.

The scaling factor comes from ``ScalingTracker.get_widget_scaling``,
which walks the widget up to its Tk/Toplevel root — so it is correct
for nested ``stk`` widgets and falls back to ``1.0`` when CTk scaling
is unavailable (non-Windows, tracker not ready).
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk

# Pixel-valued options every widget class shares (scaled where present).
_COMMON_PX = (
    "padx", "pady", "wraplength", "bd", "borderwidth", "highlightthickness",
)
# Geometry-manager padding options (may be int or (near, far) tuple).
_GEO_PAD = ("padx", "pady", "ipadx", "ipady")


def scaling(master: tk.Misc | None) -> float:
    """CTk widget-scaling factor for ``master`` (1.0 when unavailable)."""
    if master is None:
        return 1.0
    try:
        s = float(ctk.ScalingTracker.get_widget_scaling(master))
    except Exception:
        return 1.0
    return s if s > 0 else 1.0


def px(master: tk.Misc | None, value: float) -> int:
    """Scale a raw pixel ``value`` for ``master``'s DPI. Use for canvas
    coordinates, manual geometry, or any pixel math outside a widget
    option.
    """
    return round(value * scaling(master))


def _scale_num(value: Any, s: float) -> Any:
    return round(value * s) if isinstance(value, (int, float)) else value


def _scale_pad(value: Any, s: float) -> Any:
    if isinstance(value, (tuple, list)):
        return tuple(_scale_num(v, s) for v in value)
    return _scale_num(value, s)


def _scale_font(font: Any, s: float) -> Any:
    # Only tuple fonts carry a scalable numeric size at index 1.
    if (
        isinstance(font, tuple) and len(font) >= 2
        and isinstance(font[1], (int, float))
    ):
        return (font[0], round(font[1] * s), *font[2:])
    return font


class _ScaledMixin:
    """Scales pixel options / fonts on construction and configure, and
    scales geometry-manager padding on pack / grid / place.

    Subclasses set ``_SIZE_PX`` to the pixel dimensions that are safe to
    scale for that widget (``()`` for text-unit widgets whose ``width``
    counts characters).
    """

    _SIZE_PX: tuple[str, ...] = ()

    def __init__(self, master: tk.Misc | None = None, **kwargs: Any) -> None:
        self._s = scaling(master)
        super().__init__(master, **self._scaled(kwargs))

    def _scaled(self, kwargs: dict) -> dict:
        s = self._s
        for attr in self._SIZE_PX:
            if attr in kwargs:
                kwargs[attr] = _scale_num(kwargs[attr], s)
        for attr in _COMMON_PX:
            if attr in kwargs:
                kwargs[attr] = _scale_pad(kwargs[attr], s)
        if "font" in kwargs:
            kwargs["font"] = _scale_font(kwargs["font"], s)
        return kwargs

    def configure(self, cnf: dict | None = None, **kwargs: Any):
        if cnf:
            kwargs.update(cnf)
        return super().configure(**self._scaled(kwargs))

    config = configure

    def _scaled_geo(self, kwargs: dict) -> dict:
        for attr in _GEO_PAD:
            if attr in kwargs:
                kwargs[attr] = _scale_pad(kwargs[attr], self._s)
        return kwargs

    def pack(self, cnf: dict | None = None, **kwargs: Any):
        if cnf:
            kwargs.update(cnf)
        return super().pack(**self._scaled_geo(kwargs))

    def grid(self, cnf: dict | None = None, **kwargs: Any):
        if cnf:
            kwargs.update(cnf)
        return super().grid(**self._scaled_geo(kwargs))

    def place(self, cnf: dict | None = None, **kwargs: Any):
        if cnf:
            kwargs.update(cnf)
        return super().place(**self._scaled_geo(kwargs))


# ----------------------------------------------------------------------
# Widget classes. ``_SIZE_PX`` scales width/height only where those are
# pixel dimensions — Frame / Canvas. Label / Button / Entry / Check /
# Radio measure ``width`` in characters, so it is left alone (the scaled
# font already grows their footprint).

class Frame(_ScaledMixin, tk.Frame):
    _SIZE_PX = ("width", "height")


class Canvas(_ScaledMixin, tk.Canvas):
    _SIZE_PX = ("width", "height")


class Label(_ScaledMixin, tk.Label):
    pass


class Button(_ScaledMixin, tk.Button):
    pass


class Entry(_ScaledMixin, tk.Entry):
    pass


class Checkbutton(_ScaledMixin, tk.Checkbutton):
    pass


class Radiobutton(_ScaledMixin, tk.Radiobutton):
    pass


class Message(_ScaledMixin, tk.Message):
    pass
