"""Photoshop-style color picker dialog for ctk-color-picker.

Defines `ColorPickerDialog` (modal `CTkToplevel` with saturation/value
square, hue slider, HSL lightness slider, hex input, tint strip,
old/new comparison, saved colors palette, and screen eyedropper) and
the `askcolor` convenience function.
"""
import tkinter as tk

import customtkinter as ctk
from PIL import ImageTk

from .config import PickerConfig, PickerTheme
from .eyedrop import EyedropperController
from .history import ColorHistory
from .renderer import GradientRenderer
from .state import HsvState


class ColorPickerDialog(ctk.CTkToplevel):
    """Modal color picker dialog.

    Shows a saturation × value square, hue slider, HSL lightness slider,
    hex input, old/new comparison swatches, a tint strip of the current
    color, and a persistent saved colors palette.

    After the dialog closes, `self.result` holds the picked hex string
    or `None` if the user cancelled.
    """

    def __init__(self, master, initial_color: str = "#ffffff",
                 history: ColorHistory | None = None,
                 title: str = "Color Picker",
                 config: PickerConfig | None = None,
                 theme: PickerTheme | None = None):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)

        self.result: str | None = None
        self._initial = initial_color or "#ffffff"
        self._title = title
        self._history = history if history is not None else ColorHistory()
        self._config = config or PickerConfig()
        self._theme = theme or PickerTheme()
        self._renderer = GradientRenderer()
        self._state = HsvState.from_hex(self._initial)

        try:
            self._scale = ctk.ScalingTracker.get_window_scaling(self) or 1.0
        except Exception:
            self._scale = 1.0
        self._sv_w, self._sv_h = self._scaled(self._config.sv_size)
        self._sv_rend_w, self._sv_rend_h = self._scaled(self._config.sv_render_size)
        self._hue_w, self._hue_h = self._scaled(self._config.hue_size)
        self._light_w, self._light_h = self._scaled(self._config.light_size)

        self._sv_photo: ImageTk.PhotoImage | None = None
        self._hue_photo: ImageTk.PhotoImage | None = None
        self._light_photo: ImageTk.PhotoImage | None = None
        self._saved_swatches: dict[str, ctk.CTkButton] = {}
        self._recent_slots: list[ctk.CTkButton] = []
        self._tint_swatches: list[ctk.CTkButton] = []

        self._eyedropper = EyedropperController(
            dialog=self,
            on_picked=self._on_eyedrop_result,
            config=self._config.eyedrop,
        )

        self._build_ui()
        self._render_hue()
        self._render_sv()
        self._render_lightness()
        self._update_preview()
        self._refresh_recents()

        self.update_idletasks()
        self._center_on_parent(master)

        self.after(50, self._grab)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())

    def _scaled(self, size: tuple[int, int]) -> tuple[int, int]:
        return int(size[0] * self._scale), int(size[1] * self._scale)

    # --- UI build -----------------------------------------------------------

    def _build_ui(self) -> None:
        padx, pady = self._config.window_padding
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(padx=padx, pady=pady)

        self._build_compare_row(container)
        self._build_tint_strip(container)
        self._build_sv_canvas(container)
        self._build_sliders(container)
        self._build_hex_input(container)
        self._build_saved_row(container)
        self._build_buttons(container)

    def _build_compare_row(self, parent) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=(0, 12))

        self.eyedrop_btn = ctk.CTkButton(
            row, text="💧 Pick",
            width=80, height=self._config.compare_swatch_size[1],
            corner_radius=8, font=("", 11),
            fg_color=self._theme.plus_button_fg,
            hover_color=self._theme.plus_button_hover,
            command=self._eyedropper.start,
        )
        self.eyedrop_btn.pack(side="left", padx=(0, 8))

        self.new_swatch = self._make_compare_swatch(row)
        self.new_swatch.pack(side="left", padx=(0, 6))
        self.new_swatch.bind(
            "<Button-1>", lambda _e: self._load_color(self._state.to_hex()))

        self.old_swatch = self._make_compare_swatch(row)
        self.old_swatch.pack(side="left")
        self.old_swatch.bind(
            "<Button-1>", lambda _e: self._load_color(self._initial))

    def _make_compare_swatch(self, parent) -> ctk.CTkFrame:
        w, h = self._config.compare_swatch_size
        swatch = ctk.CTkFrame(
            parent, width=w, height=h,
            fg_color=self._initial,
            border_width=1, border_color=self._theme.swatch_border,
            corner_radius=8,
        )
        swatch.pack_propagate(False)
        try:
            swatch.configure(cursor="hand2")
        except Exception:
            pass
        return swatch

    def _build_tint_strip(self, parent) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=(0, 12))
        w, h = self._config.tint_btn_size
        for i in range(self._config.tint_count):
            btn = ctk.CTkButton(
                row, text="",
                width=w, height=h,
                fg_color="#000000", hover_color="#000000",
                border_width=0, corner_radius=0,
                command=lambda idx=i: self._click_tint(idx),
            )
            btn.pack(side="left", padx=0)
            self._tint_swatches.append(btn)

    def _build_sv_canvas(self, parent) -> None:
        self.sv_canvas = self._make_canvas(
            parent, self._sv_w, self._sv_h, "crosshair",
        )
        self.sv_canvas.pack()
        self.sv_canvas.bind("<Button-1>", self._on_sv_drag)
        self.sv_canvas.bind("<B1-Motion>", self._on_sv_drag)

    def _build_sliders(self, parent) -> None:
        self.light_canvas = self._make_canvas(
            parent, self._light_w, self._light_h, "sb_h_double_arrow",
        )
        self.light_canvas.pack(pady=(12, 0))
        self.light_canvas.bind("<Button-1>", self._on_lightness_drag)
        self.light_canvas.bind("<B1-Motion>", self._on_lightness_drag)

        self.hue_canvas = self._make_canvas(
            parent, self._hue_w, self._hue_h, "sb_h_double_arrow",
        )
        self.hue_canvas.pack(pady=(8, 0))
        self.hue_canvas.bind("<Button-1>", self._on_hue_drag)
        self.hue_canvas.bind("<B1-Motion>", self._on_hue_drag)

    def _make_canvas(self, parent, w: int, h: int, cursor: str) -> tk.Canvas:
        return tk.Canvas(
            parent, width=w, height=h,
            highlightthickness=1,
            highlightbackground=self._theme.canvas_border,
            bd=0, bg=self._theme.canvas_bg, cursor=cursor,
        )

    def _build_hex_input(self, parent) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=(10, 0), fill="x")
        ctk.CTkLabel(row, text="Hex", font=("", 10), width=28,
                     anchor="w").pack(side="left")

        self.hex_var = tk.StringVar(value=self._initial)
        self.hex_entry = ctk.CTkEntry(
            row, textvariable=self.hex_var,
            height=26, font=("", 11), corner_radius=8,
        )
        self.hex_entry.pack(side="left", fill="x", expand=True)
        self.hex_entry.bind("<Return>", lambda _e: self._on_hex_commit())
        self.hex_entry.bind("<FocusOut>", lambda _e: self._on_hex_commit())

    def _build_saved_row(self, parent) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(14, 4))
        ctk.CTkLabel(
            header, text="SAVED COLORS",
            font=("", 10, "bold"),
            text_color=self._theme.header_color, anchor="w",
        ).pack(side="left")
        ctk.CTkButton(
            header, text="+", width=24, height=22,
            font=("", 14, "bold"), corner_radius=8,
            fg_color=self._theme.plus_button_fg,
            hover_color=self._theme.plus_button_hover,
            command=self._save_current,
        ).pack(side="right")

        self.recents_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.recents_frame.pack(fill="x")
        self._build_recents_slots()

    def _build_recents_slots(self) -> None:
        for child in self.recents_frame.winfo_children():
            child.destroy()
        self._recent_slots = []

        rows: list[ctk.CTkFrame] = []
        for r in range(self._config.saved_rows):
            row = ctk.CTkFrame(self.recents_frame, fg_color="transparent")
            row.pack(pady=(0 if r == 0 else 4, 0))
            rows.append(row)

        total = self._config.saved_rows * self._config.saved_per_row
        for i in range(total):
            target = rows[i // self._config.saved_per_row]
            slot = ctk.CTkButton(
                target, text="",
                width=self._config.saved_btn_size,
                height=self._config.saved_btn_size,
                fg_color=self._theme.placeholder_fg,
                hover_color=self._theme.placeholder_fg,
                border_width=1,
                border_color=self._theme.placeholder_border,
                corner_radius=2,
                command=lambda: None,
            )
            slot.pack(side="left", padx=3)
            self._recent_slots.append(slot)

    def _build_buttons(self, parent) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=(14, 0), fill="x")
        ctk.CTkButton(
            row, text="OK", height=30, corner_radius=8,
            command=self._on_ok,
        ).pack(fill="x")

    # --- rendering ----------------------------------------------------------

    def _render_sv(self) -> None:
        img = self._renderer.sv_square(
            self._state.hue, self._sv_w, self._sv_h,
            self._sv_rend_w, self._sv_rend_h,
        )
        self._sv_photo = ImageTk.PhotoImage(img)
        self._set_canvas_gradient(self.sv_canvas, self._sv_photo)
        self._draw_sv_indicator()

    def _render_hue(self) -> None:
        img = self._renderer.hue_strip(self._hue_w, self._hue_h)
        self._hue_photo = ImageTk.PhotoImage(img)
        self._set_canvas_gradient(self.hue_canvas, self._hue_photo)
        self._draw_hue_indicator()

    def _render_lightness(self) -> None:
        img = self._renderer.lightness_strip(
            self._state, self._light_w, self._light_h,
        )
        self._light_photo = ImageTk.PhotoImage(img)
        self._set_canvas_gradient(self.light_canvas, self._light_photo)
        self._draw_lightness_indicator()

    @staticmethod
    def _set_canvas_gradient(canvas: tk.Canvas, photo: ImageTk.PhotoImage) -> None:
        canvas.delete("gradient")
        canvas.create_image(0, 0, anchor="nw", image=photo, tags="gradient")

    # --- indicators ---------------------------------------------------------

    def _draw_sv_indicator(self) -> None:
        cx = int(self._state.saturation * (self._sv_w - 1))
        cy = int((1 - self._state.value) * (self._sv_h - 1))
        r = max(7, int(7 * self._scale))
        self.sv_canvas.delete("indicator")
        self.sv_canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline="white", width=2, tags="indicator",
        )
        self.sv_canvas.create_oval(
            cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
            outline="black", width=1, tags="indicator",
        )

    def _draw_hue_indicator(self) -> None:
        self._draw_vbar(self.hue_canvas,
                        self._state.hue * (self._hue_w - 1),
                        self._hue_h)

    def _draw_lightness_indicator(self) -> None:
        self._draw_vbar(self.light_canvas,
                        self._state.lightness() * (self._light_w - 1),
                        self._light_h)

    @staticmethod
    def _draw_vbar(canvas: tk.Canvas, x: float, h: int) -> None:
        cx = int(x)
        canvas.delete("indicator")
        canvas.create_rectangle(
            cx - 2, 0, cx + 2, h,
            outline="white", width=2, tags="indicator",
        )

    # --- event handlers -----------------------------------------------------

    def _on_sv_drag(self, event) -> None:
        if self._eyedropper.active:
            return
        x = max(0, min(self._sv_w - 1, event.x))
        y = max(0, min(self._sv_h - 1, event.y))
        self._state.saturation = x / (self._sv_w - 1)
        self._state.value = 1 - y / (self._sv_h - 1)
        self._draw_sv_indicator()
        self._render_lightness()
        self._update_preview()

    def _on_hue_drag(self, event) -> None:
        if self._eyedropper.active:
            return
        x = max(0, min(self._hue_w - 1, event.x))
        self._state.hue = x / (self._hue_w - 1)
        self._render_sv()
        self._render_lightness()
        self._draw_hue_indicator()
        self._update_preview()

    def _on_lightness_drag(self, event) -> None:
        if self._eyedropper.active:
            return
        x = max(0, min(self._light_w - 1, event.x))
        self._state.set_lightness(x / (self._light_w - 1))
        self._draw_sv_indicator()
        self._draw_lightness_indicator()
        self._update_preview()

    def _on_hex_commit(self) -> None:
        text = self.hex_var.get().strip()
        if not text.startswith("#"):
            text = "#" + text
        if self._state.load_hex(text.lower()):
            self._render_sv()
            self._render_hue()
            self._render_lightness()
            self._update_preview()

    # --- preview / tints / recents ------------------------------------------

    def _update_preview(self) -> None:
        hex_color = self._state.to_hex()
        try:
            self.new_swatch.configure(fg_color=hex_color)
        except Exception:
            pass
        self.hex_var.set(hex_color)
        self._update_recent_highlight()
        self._update_tints()

    def _refresh_recents(self) -> None:
        self._saved_swatches = {}
        recents = self._history.all()
        for i, slot in enumerate(self._recent_slots):
            if i < len(recents):
                color = recents[i]
                slot.configure(
                    fg_color=color, hover_color=color,
                    border_color=self._theme.swatch_border, border_width=1,
                    command=lambda c=color: self._load_color(c),
                )
                self._saved_swatches[color] = slot
            else:
                slot.configure(
                    fg_color=self._theme.placeholder_fg,
                    hover_color=self._theme.placeholder_fg,
                    border_color=self._theme.placeholder_border,
                    border_width=1,
                    command=lambda: None,
                )
        self._update_recent_highlight()

    def _update_recent_highlight(self) -> None:
        current = self._state.to_hex()
        for color, btn in self._saved_swatches.items():
            if color == current:
                btn.configure(border_color=self._theme.highlight_border,
                              border_width=3)
            else:
                btn.configure(border_color=self._theme.swatch_border,
                              border_width=1)

    def _update_tints(self) -> None:
        colors = self._renderer.tint_colors(
            self._state, self._config.tint_count,
            self._config.tint_range_width,
        )
        for btn, color in zip(self._tint_swatches, colors):
            try:
                btn.configure(fg_color=color, hover_color=color)
            except Exception:
                pass

    def _click_tint(self, index: int) -> None:
        colors = self._renderer.tint_colors(
            self._state, self._config.tint_count,
            self._config.tint_range_width,
        )
        if 0 <= index < len(colors):
            self._load_color(colors[index])

    def _load_color(self, hex_str: str) -> None:
        if not self._state.load_hex(hex_str):
            return
        self._render_sv()
        self._render_hue()
        self._render_lightness()
        self._update_preview()

    def _save_current(self) -> None:
        self._history.add(self._state.to_hex())
        self._refresh_recents()

    def _on_eyedrop_result(self, hex_color: str | None) -> None:
        if hex_color is not None:
            self._state.load_hex(hex_color)
        self._render_sv()
        self._render_hue()
        self._render_lightness()
        self._update_preview()

    # --- lifecycle ----------------------------------------------------------

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _center_on_parent(self, master) -> None:
        # Two-phase clamp. The first call may run before the toplevel
        # has been mapped — winfo_width/height return 1x1 in that
        # window, which makes the bottom-edge clamp ineffective and
        # the dialog can end up extending past the taskbar. The
        # ``after_idle`` re-runs once Tk has rendered the real
        # geometry so the clamp uses correct dimensions.
        self._clamp_on_screen(master)
        try:
            self.after_idle(lambda: self._clamp_on_screen(master))
        except Exception:
            pass

    def _clamp_on_screen(self, master) -> None:
        try:
            master.update_idletasks()
            self.update_idletasks()
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width()
            mh = master.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            if w <= 1 or h <= 1:
                # Not yet mapped — skip; the after_idle pass will
                # re-run with real dimensions.
                return
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            margin = 8
            taskbar_reserve = 80
            x = mx + (mw - w) // 2
            y = my + (mh - h) // 2
            x = max(margin, min(x, sw - w - margin))
            y = max(margin, min(y, sh - h - taskbar_reserve))
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _on_ok(self) -> None:
        color = self._state.to_hex()
        self._history.add(color)
        self.result = color
        self._release_and_destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self._release_and_destroy()

    def _release_and_destroy(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def askcolor(master, initial: str = "#ffffff",
             history: ColorHistory | None = None,
             title: str = "Color Picker",
             config: PickerConfig | None = None,
             theme: PickerTheme | None = None) -> str | None:
    """Open a modal color picker dialog and return the picked color.

    This is a convenience wrapper around `ColorPickerDialog` that blocks
    until the user confirms or cancels, then returns the result.

    Args:
        master: Parent Tk widget (the dialog is centered on it and grabbed
            as modal).
        initial: Starting color as `#rrggbb`. Also shown as "Old".
        history: Custom `ColorHistory` instance. Uses a default one
            pointing at `~/.ctk_color_picker/colors.json` when None.
        title: Window title.
        config: Optional `PickerConfig` overriding sizes and counts.
        theme: Optional `PickerTheme` overriding widget colors.

    Returns:
        The picked hex string (like `"#ff5733"`), or `None` if the user
        cancelled with Esc or the window close button.

    Example:
        >>> color = askcolor(app, initial="#1f6aa5")
        >>> if color:
        ...     button.configure(fg_color=color)
    """
    dialog = ColorPickerDialog(
        master, initial_color=initial,
        history=history, title=title,
        config=config, theme=theme,
    )
    dialog.wait_window()
    return dialog.result
