"""CircularProgress — a tk.Canvas-based circular progress ring with
optional centered text. Pure Python, no CTkMaker dependency, so the
exporter can inline this module's source verbatim into generated
`.py` files.
"""
import tkinter as tk
from typing import Any

import customtkinter as ctk
from customtkinter.windows.widgets.scaling import CTkScalingBaseClass


class CircularProgress(tk.Canvas, CTkScalingBaseClass):
    """Circular progress indicator. Two arcs on a tk.Canvas — a
    full-circle track and a partial fill — plus an optional centered
    text. Call ``set(percent)`` at runtime to update; the widget
    auto-redraws on canvas resize.

    Inherits ``CTkScalingBaseClass`` so the widget participates in
    CTk's DPI-aware widget-scaling — without it, ``place(x=, y=)``
    coords would land at literal pixel positions while every CTk
    sibling's coords get scaled by the appearance scaling factor,
    leaving this widget visibly misaligned in the runtime preview.
    """

    def __init__(
        self,
        master,
        width: int = 120,
        height: int = 120,
        fg_color: str = "#4a4d50",
        progress_color: str = "#6366f1",
        thickness: int = 12,
        initial_percent: float = 50,
        show_text: bool = True,
        suffix: str = "%",
        text_color: str = "#ffffff",
        font_family: str = "TkDefaultFont",
        font_size: int = 18,
        font_bold: bool = True,
        bg_color=None,
    ):
        bg = bg_color or _circular_progress_resolve_bg(master)
        # Construct the underlying tk.Canvas with CTk-scaled pixel
        # dimensions so the widget renders at the same scale as its
        # siblings on hi-DPI displays. CTkScalingBaseClass.__init__
        # registers ``_set_scaling`` for live appearance changes.
        tk.Canvas.__init__(
            self,
            master,
            highlightthickness=0,
            bd=0,
            bg=bg,
        )
        CTkScalingBaseClass.__init__(self, scaling_type="widget")
        self._desired_width = int(width)
        self._desired_height = int(height)
        try:
            tk.Canvas.configure(
                self,
                width=self._apply_widget_scaling(self._desired_width),
                height=self._apply_widget_scaling(self._desired_height),
            )
        except tk.TclError:
            pass
        self._percent = max(0, min(100, float(initial_percent)))
        self._fg_color = fg_color
        self._progress_color = progress_color
        self._thickness = max(1, int(thickness))
        self._show_text = bool(show_text)
        self._suffix = suffix
        self._text_color = text_color
        weight = "bold" if font_bold else "normal"
        self._font = (font_family, int(font_size), weight)
        self.bind("<Configure>", self._redraw)
        self._redraw()

    # ------------------------------------------------------------------
    # Geometry manager overrides — scale x/y/width/height args so the
    # widget aligns with CTk siblings on hi-DPI displays. Mirrors what
    # ``CTkBaseClass`` does for first-class CTk widgets.
    # ------------------------------------------------------------------
    def place(self, **kwargs):
        return super().place(**self._apply_argument_scaling(kwargs))

    def pack(self, **kwargs):
        return super().pack(**self._apply_argument_scaling(kwargs))

    def grid(self, **kwargs):
        return super().grid(**self._apply_argument_scaling(kwargs))

    def _set_scaling(self, new_widget_scaling, new_window_scaling):
        """Called by CTk's appearance manager when the user changes
        scaling at runtime. Re-apply width/height in the new pixel
        space so the canvas stays sized correctly.
        """
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        try:
            tk.Canvas.configure(
                self,
                width=self._apply_widget_scaling(self._desired_width),
                height=self._apply_widget_scaling(self._desired_height),
            )
        except tk.TclError:
            pass
        self._redraw()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set(self, percent: float) -> None:
        self._percent = max(0, min(100, float(percent)))
        self._redraw()

    def get(self) -> float:
        return self._percent

    def configure(self, **kwargs: Any) -> None:
        dirty = False
        for key in list(kwargs):
            if key == "width":
                self._desired_width = int(kwargs.pop(key))
                try:
                    tk.Canvas.configure(
                        self,
                        width=self._apply_widget_scaling(
                            self._desired_width,
                        ),
                    )
                except tk.TclError:
                    pass
                dirty = True
                continue
            if key == "height":
                self._desired_height = int(kwargs.pop(key))
                try:
                    tk.Canvas.configure(
                        self,
                        height=self._apply_widget_scaling(
                            self._desired_height,
                        ),
                    )
                except tk.TclError:
                    pass
                dirty = True
                continue
            if key == "fg_color":
                self._fg_color = kwargs.pop(key)
                dirty = True
            elif key == "progress_color":
                self._progress_color = kwargs.pop(key)
                dirty = True
            elif key == "thickness":
                self._thickness = max(1, int(kwargs.pop(key)))
                dirty = True
            elif key == "initial_percent":
                self._percent = max(0, min(100, float(kwargs.pop(key))))
                dirty = True
            elif key == "show_text":
                self._show_text = bool(kwargs.pop(key))
                dirty = True
            elif key == "suffix":
                self._suffix = kwargs.pop(key)
                dirty = True
            elif key == "text_color":
                self._text_color = kwargs.pop(key)
                dirty = True
            elif key == "font_family":
                self._font = (kwargs.pop(key), self._font[1], self._font[2])
                dirty = True
            elif key == "font_size":
                size = int(kwargs.pop(key))
                self._font = (self._font[0], size, self._font[2])
                dirty = True
            elif key == "font_bold":
                weight = "bold" if kwargs.pop(key) else "normal"
                self._font = (self._font[0], self._font[1], weight)
                dirty = True
        if kwargs:
            super().configure(**kwargs)
        if dirty:
            self._redraw()

    config = configure

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _redraw(self, _event=None) -> None:
        self.delete("all")
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        size = min(w, h)
        pad = self._thickness // 2 + 2
        # Center the ring inside the canvas (handles non-square sizes)
        offset_x = (w - size) // 2
        offset_y = (h - size) // 2
        x1 = offset_x + pad
        y1 = offset_y + pad
        x2 = offset_x + size - pad
        y2 = offset_y + size - pad
        # Track ring
        self.create_arc(
            x1, y1, x2, y2,
            start=0, extent=359.999,
            style="arc",
            outline=self._fg_color,
            width=self._thickness,
        )
        # Progress arc — clockwise from top
        if self._percent > 0:
            extent = -360.0 * (self._percent / 100.0)
            # Tk's arc widget rejects extent <= -360 (full circle is
            # impossible to render as an open arc), so cap just inside.
            extent = max(extent, -359.999)
            self.create_arc(
                x1, y1, x2, y2,
                start=90, extent=extent,
                style="arc",
                outline=self._progress_color,
                width=self._thickness,
            )
        if self._show_text:
            sfx = "" if self._suffix == "none" else self._suffix
            txt = f"{int(self._percent)}{sfx}"
            self.create_text(
                w / 2, h / 2,
                text=txt,
                fill=self._text_color,
                font=self._font,
            )


def _circular_progress_resolve_bg(master) -> str:
    """Walk up the master chain looking for a CTk widget with a solid
    fg_color so the canvas's tk-level bg matches the parent surface.
    Falls back to the CTkFrame default.
    """
    w = master
    for _ in range(20):
        if w is None:
            break
        try:
            bg = w.cget("fg_color")
        except (AttributeError, tk.TclError):
            break
        if bg == "transparent":
            w = getattr(w, "master", None)
            continue
        if isinstance(bg, (tuple, list)):
            mode = (ctk.get_appearance_mode() or "light").lower()
            return bg[1] if mode == "dark" and len(bg) > 1 else bg[0]
        if isinstance(bg, str) and bg.startswith("#"):
            return bg
        break
    return "#2b2b2b"
