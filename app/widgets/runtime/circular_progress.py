"""CircularProgress — a tk.Canvas-based circular progress ring with
optional centered text. Pure Python, no CTkMaker dependency, so the
exporter can inline this module's source verbatim into generated
`.py` files.
"""
import tkinter as tk

import customtkinter as ctk


class CircularProgress(tk.Canvas):
    """Circular progress indicator. Two arcs on a tk.Canvas — a
    full-circle track and a partial fill — plus an optional centered
    text. Call ``set(percent)`` at runtime to update; the widget
    auto-redraws on canvas resize.
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
        text_format: str = "{percent}%",
        text_color: str = "#ffffff",
        font_size: int = 18,
        font_bold: bool = True,
        bg_color=None,
    ):
        bg = bg_color or _circular_progress_resolve_bg(master)
        super().__init__(
            master,
            width=width,
            height=height,
            highlightthickness=0,
            bd=0,
            bg=bg,
        )
        self._percent = max(0, min(100, float(initial_percent)))
        self._fg_color = fg_color
        self._progress_color = progress_color
        self._thickness = max(1, int(thickness))
        self._show_text = bool(show_text)
        self._text_format = text_format
        self._text_color = text_color
        weight = "bold" if font_bold else "normal"
        self._font = ("TkDefaultFont", int(font_size), weight)
        self.bind("<Configure>", self._redraw)
        self._redraw()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set(self, percent: float) -> None:
        self._percent = max(0, min(100, float(percent)))
        self._redraw()

    def get(self) -> float:
        return self._percent

    def configure(self, **kwargs) -> None:
        dirty = False
        for key in list(kwargs):
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
            elif key == "text_format":
                self._text_format = kwargs.pop(key)
                dirty = True
            elif key == "text_color":
                self._text_color = kwargs.pop(key)
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
            try:
                txt = self._text_format.format(
                    percent=int(self._percent),
                    value=self._percent,
                )
            except (KeyError, IndexError, ValueError):
                txt = f"{int(self._percent)}%"
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
            mode = ctk.get_appearance_mode().lower()
            return bg[1] if mode == "dark" and len(bg) > 1 else bg[0]
        if isinstance(bg, str) and bg.startswith("#"):
            return bg
        break
    return "#2b2b2b"
