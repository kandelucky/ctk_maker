"""Screen-wide eyedropper controller for ctk-color-picker.

`EyedropperController` manages the eyedrop lifecycle: withdraw the
dialog, grab a full screen screenshot, show a fullscreen transparent
overlay, follow the cursor with a live preview bubble, display a
top-center hint toast, and sample the clicked pixel.
"""
import tkinter as tk
from typing import Callable

from .config import EyedropConfig


class EyedropperController:
    """Screen-wide eyedropper mode for a Toplevel dialog.

    Workflow:
        1. `start()` — hide the dialog, take a full screen screenshot,
           create a fullscreen transparent overlay, a cursor-following
           preview bubble, and a top-center hint toast.
        2. While active, the preview bubble shows the color under the
           cursor (read from the saved screenshot).
        3. On click anywhere: read the clicked pixel from the saved
           screenshot and call `on_picked(hex_str)`.
        4. On Escape: call `on_picked(None)`.
        5. In either case, clean up all widgets and restore the dialog.

    The controller never touches the dialog's color state directly.
    The caller is responsible for applying the picked color and
    re-rendering its widgets inside `on_picked`.
    """

    def __init__(self, dialog: tk.Tk | tk.Toplevel,
                 on_picked: Callable[[str | None], None],
                 config: EyedropConfig | None = None):
        self.dialog = dialog
        self.on_picked = on_picked
        self.config = config or EyedropConfig()

        self._active: bool = False
        self._screen_shot = None
        self._overlay: tk.Toplevel | None = None
        self._preview_top: tk.Toplevel | None = None
        self._preview_canvas: tk.Canvas | None = None
        self._hint_top: tk.Toplevel | None = None

    # --- public -------------------------------------------------------------

    def start(self) -> None:
        """Enter eyedrop mode.

        Hides the parent dialog, captures a screenshot, and sets up the
        overlay, preview bubble, and hint toast. Safe to call while
        already active (becomes a no-op in that case).
        """
        if self._active:
            return
        self._active = True
        self.dialog.withdraw()
        self.dialog.update_idletasks()
        self.dialog.after(self.config.withdraw_delay_ms, self._begin_capture)

    @property
    def active(self) -> bool:
        """True while the eyedrop overlay is visible."""
        return self._active

    # --- setup --------------------------------------------------------------

    def _begin_capture(self) -> None:
        try:
            from PIL import ImageGrab
            self._screen_shot = ImageGrab.grab()
        except Exception:
            self._finish(None)
            return

        try:
            self._build_overlay()
            self._build_preview_bubble()
            self._build_hint_toast()
        except Exception:
            self._finish(None)

    def _build_overlay(self) -> None:
        # Cover the full physical desktop via winfo_vroot*. `-fullscreen`
        # would use Tk's cached `winfo_screenwidth` which on Windows with
        # DPI scaling (or CTk's `SetProcessDpiAwareness(2)` set after Tk
        # init) returns the *logical* screen size — leaving the right and
        # bottom strips uncovered and the eyedropper unable to sample
        # pixels there. vroot reports the full virtual desktop in
        # physical pixels and also handles multi-monitor.
        overlay = tk.Toplevel(self.dialog)
        overlay.attributes("-alpha", self.config.overlay_alpha)
        overlay.overrideredirect(True)
        vw = self.dialog.winfo_vrootwidth()
        vh = self.dialog.winfo_vrootheight()
        vx = self.dialog.winfo_vrootx()
        vy = self.dialog.winfo_vrooty()
        overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")
        overlay.attributes("-topmost", True)
        overlay.configure(cursor="crosshair", bg="black")
        overlay.bind("<Button-1>", self._on_click)
        overlay.bind("<Motion>", self._on_motion)
        overlay.bind("<Escape>", lambda _e: self._finish(None))
        overlay.protocol("WM_DELETE_WINDOW", lambda: self._finish(None))
        overlay.focus_force()
        self._overlay = overlay

    def _build_preview_bubble(self) -> None:
        size = self.config.preview_size
        try:
            top = tk.Toplevel(self.dialog)
            top.overrideredirect(True)
            top.attributes("-topmost", True)

            try:
                top.attributes("-transparentcolor", self.config.transparent_key)
                canvas_bg = self.config.transparent_key
            except tk.TclError:
                canvas_bg = "#1e1e1e"

            canvas = tk.Canvas(
                top, width=size, height=size,
                bg=canvas_bg, highlightthickness=0, bd=0,
            )
            canvas.pack()
            canvas.create_oval(
                1, 1, size - 1, size - 1,
                fill="#000000", outline="#ffffff", width=2,
                tags="color_dot",
            )
            self._preview_top = top
            self._preview_canvas = canvas
        except Exception:
            self._preview_top = None
            self._preview_canvas = None

    def _build_hint_toast(self) -> None:
        try:
            top = tk.Toplevel(self.dialog)
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            top.configure(bg=self.config.hint_bg)

            label = tk.Label(
                top,
                text=self.config.hint_text,
                bg=self.config.hint_bg, fg=self.config.hint_fg,
                font=("", 11, "bold"),
                padx=self.config.hint_padx, pady=self.config.hint_pady,
            )
            label.pack()

            top.update_idletasks()
            w = top.winfo_reqwidth()
            h = top.winfo_reqheight()
            # vroot for the same reason `_build_overlay` uses it: under
            # CTk's DPI awareness `winfo_screenwidth` returns the logical
            # width and the toast would render off-center on the physical
            # desktop.
            try:
                sw = self.dialog.winfo_vrootwidth()
                sx = self.dialog.winfo_vrootx()
            except Exception:
                sw = 1920
                sx = 0
            x = sx + max(0, (sw - w) // 2)
            y = self.config.hint_y
            top.geometry(f"{w}x{h}+{x}+{y}")

            self._hint_top = top
            top.after(self.config.hint_visible_ms,
                      lambda: self._fade_hint(1.0))
        except Exception:
            self._hint_top = None

    # --- fade + hide hint ---------------------------------------------------

    def _fade_hint(self, alpha: float) -> None:
        if self._hint_top is None:
            return
        alpha -= self.config.fade_step_alpha
        if alpha <= 0:
            self._hide_hint()
            return
        try:
            self._hint_top.attributes("-alpha", alpha)
            self._hint_top.after(
                self.config.fade_step_ms,
                lambda: self._fade_hint(alpha),
            )
        except Exception:
            self._hide_hint()

    def _hide_hint(self) -> None:
        if self._hint_top is not None:
            try:
                self._hint_top.destroy()
            except Exception:
                pass
            self._hint_top = None

    # --- event handlers -----------------------------------------------------

    def _on_motion(self, event) -> None:
        if self._screen_shot is None or self._preview_top is None:
            return

        x = event.x_root
        y = event.y_root

        try:
            pixel = self._screen_shot.getpixel((x, y))
            if isinstance(pixel, (tuple, list)) and len(pixel) >= 3:
                hex_color = "#{:02x}{:02x}{:02x}".format(
                    pixel[0], pixel[1], pixel[2])
                if self._preview_canvas is not None:
                    self._preview_canvas.itemconfigure(
                        "color_dot", fill=hex_color)
        except Exception:
            pass

        size = self.config.preview_size
        offset = self.config.preview_offset
        try:
            sw = self.dialog.winfo_screenwidth()
            sh = self.dialog.winfo_screenheight()
        except Exception:
            sw, sh = 9999, 9999
        px = x + offset if x + offset + size < sw else x - offset - size
        py = y + offset if y + offset + size < sh else y - offset - size
        try:
            self._preview_top.geometry(f"+{px}+{py}")
        except Exception:
            pass

    def _on_click(self, event) -> None:
        hex_color: str | None = None
        try:
            x = event.x_root
            y = event.y_root
            if self._screen_shot is not None:
                pixel = self._screen_shot.getpixel((x, y))
                if isinstance(pixel, (tuple, list)) and len(pixel) >= 3:
                    hex_color = "#{:02x}{:02x}{:02x}".format(
                        pixel[0], pixel[1], pixel[2])
        except Exception:
            pass
        self._finish(hex_color)

    # --- teardown -----------------------------------------------------------

    def _finish(self, hex_color: str | None) -> None:
        self._hide_hint()

        if self._preview_top is not None:
            try:
                self._preview_top.destroy()
            except Exception:
                pass
            self._preview_top = None
            self._preview_canvas = None

        if self._overlay is not None:
            try:
                self._overlay.destroy()
            except Exception:
                pass
            self._overlay = None

        if self._screen_shot is not None:
            try:
                self._screen_shot.close()
            except Exception:
                pass
            self._screen_shot = None
        self._active = False

        try:
            self.dialog.deiconify()
            self.dialog.lift()
            self.dialog.focus_force()
        except Exception:
            pass

        try:
            self.on_picked(hex_color)
        except Exception:
            pass
