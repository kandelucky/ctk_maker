"""CTkButton Properties panel — spacing playground.

Standalone sandbox that mirrors the CTkButton Properties panel visually
and exposes every spacing / sizing constant as a live slider so you can
tune the feel of the panel without touching the real app.

Run:
    python tools/ctk_button_spacing_playground.py

Nothing in this file touches app/. When you settle on values, click
"Print values" and paste the printed block into
`app/ui/properties_panel.py`.
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


# =====================================================================
# Default parameters — starting values match the current real panel.
# =====================================================================
DEFAULTS: dict[str, int] = {
    # Group spacing
    "group_pady_top": 4,
    "group_pady_bottom": 2,
    # Subgroup spacing
    "subgroup_pady_top": 2,
    "subgroup_pady_bottom": 1,
    # Row spacing
    "row_pady_top": 0,
    "row_pady_bottom": 0,
    "row_padx_left": 2,
    "row_padx_right": 5,
    "subgroup_indent": 14,
    # Header heights
    "group_header_height": 22,
    "subgroup_header_height": 12,
    # Row height (0 = auto, >0 = forced via pack_propagate(False))
    "row_height": 0,
    # Label font sizes
    "group_label_font_size": 10,
    "subgroup_label_font_size": 9,
    "row_label_font_size": 10,
    # Sizes
    "row_label_width": 60,
    "entry_height": 18,
    "button_height": 18,
    "dropdown_height": 22,
    "checkbox_size": 14,
    # Panel
    "panel_width": 320,
    # Advanced
    "title_pady_top": 5,
    "title_pady_bottom": 2,
    "title_font_size": 13,
    "type_bar_pady_bottom": 2,
    "type_bar_font_size": 11,
    "body_padx": 6,
    "body_pady_top": 0,
    "row_label_padx_left": 4,
    "entry_width": 52,
    "mini_label_width": 16,
}

PARAM_RANGES: dict[str, tuple[int, int]] = {
    "group_pady_top": (0, 20),
    "group_pady_bottom": (0, 20),
    "subgroup_pady_top": (0, 20),
    "subgroup_pady_bottom": (0, 20),
    "row_pady_top": (0, 10),
    "row_pady_bottom": (0, 10),
    "row_padx_left": (0, 20),
    "row_padx_right": (0, 20),
    "subgroup_indent": (0, 30),
    "group_header_height": (14, 30),
    "subgroup_header_height": (8, 20),
    "row_height": (0, 30),
    "group_label_font_size": (8, 14),
    "subgroup_label_font_size": (8, 13),
    "row_label_font_size": (8, 13),
    "row_label_width": (40, 120),
    "entry_height": (14, 32),
    "button_height": (14, 32),
    "dropdown_height": (18, 36),
    "checkbox_size": (10, 24),
    "panel_width": (220, 500),
    "title_pady_top": (0, 20),
    "title_pady_bottom": (0, 20),
    "title_font_size": (9, 18),
    "type_bar_pady_bottom": (0, 20),
    "type_bar_font_size": (8, 16),
    "body_padx": (0, 20),
    "body_pady_top": (0, 20),
    "row_label_padx_left": (0, 20),
    "entry_width": (30, 100),
    "mini_label_width": (8, 40),
}

PARAM_GROUPS: list[tuple[str, list[str]]] = [
    ("Group spacing", ["group_pady_top", "group_pady_bottom"]),
    ("Subgroup spacing", ["subgroup_pady_top", "subgroup_pady_bottom"]),
    ("Row spacing", [
        "row_pady_top", "row_pady_bottom",
        "row_padx_left", "row_padx_right",
        "subgroup_indent",
    ]),
    ("Heights", [
        "group_header_height", "subgroup_header_height", "row_height",
    ]),
    ("Label fonts", [
        "group_label_font_size",
        "subgroup_label_font_size",
        "row_label_font_size",
    ]),
    ("Sizes", [
        "row_label_width",
        "entry_height", "button_height",
        "dropdown_height", "checkbox_size",
    ]),
    ("Panel", ["panel_width"]),
    ("Advanced", [
        "title_pady_top", "title_pady_bottom", "title_font_size",
        "type_bar_pady_bottom", "type_bar_font_size",
        "body_padx", "body_pady_top",
        "row_label_padx_left",
        "entry_width", "mini_label_width",
    ]),
]

# Mirrors colors from properties_panel.py so the mock matches the real one.
VALUE_BG = "#2d2d2d"
HEADER_BG = "#2a2a2a"
STATIC_FG = "#888888"
HEADER_FG = "#cccccc"
SUBGROUP_FG = "#aaaaaa"
TYPE_LABEL_FG = "#3b8ed0"


class MockPropertiesPanel(ctk.CTkFrame):
    """A schema-free mock that only draws the CTkButton panel layout."""

    def __init__(self, master, params: dict[str, int]):
        super().__init__(master)
        self.params = params
        self._row_padx_extra = 0   # set to subgroup_indent inside subgroups

        self.title = ctk.CTkLabel(self, text="Properties")
        self.type_bar = ctk.CTkLabel(
            self, text="CTkButton", text_color=TYPE_LABEL_FG, anchor="w",
        )
        self.body = ctk.CTkFrame(self, fg_color="transparent")

        self._repack_chrome()
        self.rebuild()

    def _repack_chrome(self) -> None:
        """(Re)pack title, type bar, and body with current params."""
        p = self.params
        self.title.pack_forget()
        self.type_bar.pack_forget()
        self.body.pack_forget()

        self.title.configure(
            font=("Segoe UI", p["title_font_size"], "bold"),
        )
        self.title.pack(
            pady=(p["title_pady_top"], p["title_pady_bottom"]), padx=10,
        )

        self.type_bar.configure(
            font=("Segoe UI", p["type_bar_font_size"], "bold"),
        )
        self.type_bar.pack(
            fill="x", pady=(0, p["type_bar_pady_bottom"]), padx=8,
        )

        self.body.pack(
            fill="both", expand=True,
            padx=p["body_padx"], pady=(p["body_pady_top"], 4),
        )

    # ------------------------------------------------------------------
    # Rebuild
    # ------------------------------------------------------------------
    def rebuild(self) -> None:
        # Let content dictate size during build, lock width afterwards.
        self.pack_propagate(True)
        self._repack_chrome()
        for child in self.body.winfo_children():
            child.destroy()
        self._row_padx_extra = 0

        self._group("Geometry")
        self._paired_number_row("Position", [("X", "120"), ("Y", "120")])
        self._paired_number_row("Size", [("W", "140"), ("H", "32")])

        self._group("Rectangle")
        self._subgroup("Corners")
        self._single_row("Roundness", self._mk_entry, "6")
        self._subgroup("Border")
        self._single_row("Thickness", self._mk_entry, "0")
        self._single_row("Color", self._mk_color, "#565b5e")
        self._end_subgroup()

        self._group("State")
        self._single_row("Disabled", self._mk_checkbox, False)

        self._group("Main Colors")
        self._single_row("Background", self._mk_color, "#1f6aa5")
        self._single_row("Hover", self._mk_color, "#144870")

        self._group("Text")
        self._single_row("Label", self._mk_entry_wide, "CTkButton")
        self._subgroup("Style")
        self._paired_mixed_row("Size", [("", "13", "entry"),
                                        ("Best Fit", False, "checkbox")])
        self._paired_mixed_row("Style", [("Bold", False, "checkbox"),
                                         ("Italic", False, "checkbox")])
        self._paired_mixed_row("Decoration",
                               [("Underline", False, "checkbox"),
                                ("Strike", False, "checkbox")])
        self._subgroup("Alignment")
        self._single_row("Align", self._mk_dropdown, "Center")
        self._subgroup("Color")
        self._single_row("Normal", self._mk_color, "#ffffff")
        self._single_row("Disabled", self._mk_color, "#a0a0a0")
        self._end_subgroup()

        self._group("Image & Alignment")
        self._single_row("Image", self._mk_image_picker, "(no image)")
        self._paired_number_row("Size", [("W", "20"), ("H", "20")])
        self._single_row("Position", self._mk_dropdown, "left")

        # Lock the panel to `panel_width` while keeping whatever height
        # the content naturally required. Must happen after all children
        # are packed so winfo_reqheight reflects the full layout.
        self.update_idletasks()
        required_h = self.winfo_reqheight()
        self.configure(
            width=self.params["panel_width"], height=required_h,
        )
        self.pack_propagate(False)

    # ------------------------------------------------------------------
    # Group / subgroup headers
    # ------------------------------------------------------------------
    def _group(self, name: str) -> None:
        self._end_subgroup()
        p = self.params
        wrap = ctk.CTkFrame(
            self.body, fg_color=HEADER_BG,
            height=p["group_header_height"], corner_radius=0,
        )
        wrap.pack(fill="x", pady=(p["group_pady_top"], p["group_pady_bottom"]))
        wrap.pack_propagate(False)

        arrow = ctk.CTkLabel(
            wrap, text="▼",
            font=("Segoe UI", max(8, p["group_label_font_size"] - 1), "bold"),
            text_color=SUBGROUP_FG, fg_color=HEADER_BG, width=12,
            height=max(8, p["group_header_height"] - 6),
        )
        arrow.pack(side="left", padx=(6, 2))

        header = ctk.CTkLabel(
            wrap, text=name, fg_color=HEADER_BG,
            font=("Segoe UI", p["group_label_font_size"], "bold"),
            text_color=HEADER_FG, anchor="w",
            height=max(8, p["group_header_height"] - 6),
        )
        header.pack(side="left", padx=(2, 6))

    def _subgroup(self, name: str) -> None:
        self._row_padx_extra = 0
        p = self.params
        header = ctk.CTkLabel(
            self.body, text=name,
            font=("Segoe UI", p["subgroup_label_font_size"], "bold"),
            text_color=SUBGROUP_FG, anchor="w",
            height=p["subgroup_header_height"],
        )
        header.pack(
            fill="x",
            pady=(p["subgroup_pady_top"], p["subgroup_pady_bottom"]),
            padx=4,
        )
        self._row_padx_extra = p["subgroup_indent"] - p["row_padx_left"]

    def _end_subgroup(self) -> None:
        self._row_padx_extra = 0

    # ------------------------------------------------------------------
    # Row factories
    # ------------------------------------------------------------------
    def _new_row(self) -> ctk.CTkFrame:
        p = self.params
        row_kwargs: dict = {"fg_color": "transparent"}
        if p["row_height"] > 0:
            row_kwargs["height"] = p["row_height"]
        row = ctk.CTkFrame(self.body, **row_kwargs)
        left = p["row_padx_left"] + self._row_padx_extra
        row.pack(
            fill="x",
            pady=(p["row_pady_top"], p["row_pady_bottom"]),
            padx=(left, p["row_padx_right"]),
        )
        if p["row_height"] > 0:
            row.pack_propagate(False)
        return row

    def _row_label(self, row, text: str) -> ctk.CTkLabel:
        p = self.params
        label_kwargs: dict = {
            "text": text, "anchor": "w",
            "font": ("Segoe UI", p["row_label_font_size"]),
            "text_color": STATIC_FG,
            "width": p["row_label_width"],
        }
        if p["row_height"] > 0:
            label_kwargs["height"] = max(8, p["row_height"] - 2)
        label = ctk.CTkLabel(row, **label_kwargs)
        label.pack(side="left", padx=(p["row_label_padx_left"], 0))
        return label

    def _single_row(self, label_text: str, factory, value) -> None:
        row = self._new_row()
        self._row_label(row, label_text)
        factory(row, value)

    def _paired_number_row(self, label_text: str,
                           pairs: list[tuple[str, str]]) -> None:
        row = self._new_row()
        self._row_label(row, label_text)
        fs = self.params["row_label_font_size"]
        mini_w = self.params["mini_label_width"]
        for i, (mini, val) in enumerate(pairs):
            ctk.CTkLabel(
                row, text=mini, width=mini_w, anchor="e",
                font=("Segoe UI", fs), text_color=STATIC_FG,
            ).pack(side="left", padx=(6 if i > 0 else 0, 4))
            self._mk_entry(row, val, fill=False)

    def _paired_mixed_row(self, label_text: str,
                          items: list[tuple[str, object, str]]) -> None:
        row = self._new_row()
        self._row_label(row, label_text)
        fs = self.params["row_label_font_size"]
        for i, (sub, val, kind) in enumerate(items):
            if sub:
                ctk.CTkLabel(
                    row, text=sub, anchor="e", font=("Segoe UI", fs),
                    text_color=STATIC_FG,
                ).pack(side="left", padx=(8 if i > 0 else 0, 4))
            if kind == "entry":
                self._mk_entry(row, val, fill=False)
            elif kind == "checkbox":
                self._mk_checkbox(row, val)

    # ------------------------------------------------------------------
    # Editor factories
    # ------------------------------------------------------------------
    def _mk_entry(self, parent, value, *, fill: bool = True) -> None:
        entry = ctk.CTkEntry(
            parent, height=self.params["entry_height"],
            width=self.params["entry_width"], corner_radius=3,
            font=("Segoe UI", 10), fg_color=VALUE_BG,
            border_width=0,
        )
        entry.insert(0, str(value))
        entry.pack(side="left", padx=(0, 4), fill="x" if fill else None,
                   expand=fill)

    def _mk_entry_wide(self, parent, value) -> None:
        entry = ctk.CTkEntry(
            parent, height=self.params["entry_height"],
            corner_radius=3, font=("Segoe UI", 10), fg_color=VALUE_BG,
            border_width=0,
        )
        entry.insert(0, str(value))
        entry.pack(side="left", padx=(0, 4), fill="x", expand=True)

    def _mk_color(self, parent, value) -> None:
        btn = ctk.CTkButton(
            parent, text="", height=self.params["button_height"],
            width=52, corner_radius=3, fg_color=value, hover_color=value,
        )
        btn.pack(side="left", padx=(0, 4), fill="x", expand=True)

    def _mk_checkbox(self, parent, value) -> None:
        size = self.params["checkbox_size"]
        cb = ctk.CTkCheckBox(
            parent, text="", width=size, height=size,
            checkbox_width=size, checkbox_height=size,
        )
        if value:
            cb.select()
        cb.pack(side="left", padx=(0, 4))

    def _mk_dropdown(self, parent, value) -> None:
        menu = ctk.CTkOptionMenu(
            parent, values=[str(value)],
            height=self.params["dropdown_height"],
            font=("Segoe UI", 10), dropdown_font=("Segoe UI", 10),
            corner_radius=3,
        )
        menu.set(str(value))
        menu.pack(side="left", padx=(0, 4), fill="x", expand=True)

    def _mk_image_picker(self, parent, value) -> None:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            wrap, text=str(value), font=("Segoe UI", 10),
            text_color=STATIC_FG, anchor="w",
        ).pack(fill="x")
        btn_row = ctk.CTkFrame(wrap, fg_color="transparent")
        btn_row.pack(fill="x", pady=(1, 0))
        ctk.CTkButton(
            btn_row, text="Browse...",
            height=self.params["button_height"], width=70, corner_radius=3,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            btn_row, text="Clear",
            height=self.params["button_height"], width=50, corner_radius=3,
            font=("Segoe UI", 10),
        ).pack(side="left")


# =====================================================================
# Controls panel
# =====================================================================
class ControlsPanel(ctk.CTkScrollableFrame):
    def __init__(self, master, params: dict[str, int], on_change):
        super().__init__(master, width=340, label_text="Spacing controls")
        self.params = params
        self.on_change = on_change
        self.value_labels: dict[str, ctk.CTkLabel] = {}
        self.sliders: dict[str, ctk.CTkSlider] = {}
        self.slot_a: dict[str, int] | None = None
        self.slot_b: dict[str, int] | None = None

        for group_name, keys in PARAM_GROUPS:
            ctk.CTkLabel(
                self, text=group_name,
                font=("Segoe UI", 12, "bold"), text_color=HEADER_FG,
                anchor="w",
            ).pack(fill="x", pady=(10, 2), padx=4)
            for key in keys:
                self._add_slider(key)

        # --- Save/Load slot row -----------------------------------------
        slot_row = ctk.CTkFrame(self, fg_color="transparent")
        slot_row.pack(fill="x", pady=(18, 4), padx=4)
        self.save_a_btn = ctk.CTkButton(
            slot_row, text="Save A", command=self._save_a,
            width=66, height=26,
        )
        self.save_a_btn.pack(side="left", padx=(0, 3))
        self.load_a_btn = ctk.CTkButton(
            slot_row, text="Load A", command=self._load_a,
            width=66, height=26, state="disabled",
            fg_color="#3c3c3c", hover_color="#4a4a4a",
        )
        self.load_a_btn.pack(side="left", padx=(0, 10))
        self.save_b_btn = ctk.CTkButton(
            slot_row, text="Save B", command=self._save_b,
            width=66, height=26,
        )
        self.save_b_btn.pack(side="left", padx=(0, 3))
        self.load_b_btn = ctk.CTkButton(
            slot_row, text="Load B", command=self._load_b,
            width=66, height=26, state="disabled",
            fg_color="#3c3c3c", hover_color="#4a4a4a",
        )
        self.load_b_btn.pack(side="left")

        # --- Reset / print row ------------------------------------------
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 8), padx=4)
        ctk.CTkButton(
            btn_row, text="Reset", command=self._reset, width=80, height=28,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btn_row, text="Print values", command=self._print_values,
            width=120, height=28,
        ).pack(side="left")

    def _add_slider(self, key: str) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=2, padx=4)

        ctk.CTkLabel(
            row, text=key, width=170, anchor="w", font=("Segoe UI", 10),
            text_color=STATIC_FG,
        ).pack(side="left")

        lo, hi = PARAM_RANGES[key]
        value = self.params[key]
        val_label = ctk.CTkLabel(
            row, text=str(value), width=30, anchor="e",
            font=("Segoe UI", 10, "bold"), text_color=HEADER_FG,
        )
        val_label.pack(side="right")
        self.value_labels[key] = val_label

        slider = ctk.CTkSlider(
            row, from_=lo, to=hi,
            number_of_steps=max(1, hi - lo),
            command=lambda v, k=key: self._on_slide(k, v),
        )
        slider.set(value)
        slider.pack(side="right", padx=(8, 6), fill="x", expand=True)
        self.sliders[key] = slider

    def _on_slide(self, key: str, value: float) -> None:
        iv = int(round(value))
        if self.params[key] == iv:
            return
        self.params[key] = iv
        self.value_labels[key].configure(text=str(iv))
        self.on_change()

    def _apply_params(self, new_values: dict[str, int]) -> None:
        """Write new values into params and sync sliders + labels + mock."""
        self.params.update(new_values)
        for key, slider in self.sliders.items():
            value = self.params[key]
            slider.set(value)
            self.value_labels[key].configure(text=str(value))
        self.on_change()

    def _reset(self) -> None:
        self._apply_params(DEFAULTS)

    def _save_a(self) -> None:
        self.slot_a = dict(self.params)
        self.load_a_btn.configure(
            state="normal", fg_color=["#3a7ebf", "#1f538d"],
            hover_color=["#325882", "#14375e"],
        )

    def _load_a(self) -> None:
        if self.slot_a is not None:
            self._apply_params(self.slot_a)

    def _save_b(self) -> None:
        self.slot_b = dict(self.params)
        self.load_b_btn.configure(
            state="normal", fg_color=["#3a7ebf", "#1f538d"],
            hover_color=["#325882", "#14375e"],
        )

    def _load_b(self) -> None:
        if self.slot_b is not None:
            self._apply_params(self.slot_b)

    def _print_values(self) -> None:
        print("=" * 60)
        print("# Paste into app/ui/properties_panel.py")
        print("=" * 60)
        for key, value in self.params.items():
            print(f"{key} = {value}")
        print("=" * 60)


# =====================================================================
# Main window
# =====================================================================
class Playground(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CTkButton Properties — Spacing Playground")
        self.geometry("900x780")
        ctk.set_appearance_mode("dark")

        self.params = dict(DEFAULTS)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Left — mock panel inside a scroll view so very tall spacings still fit.
        left_wrap = ctk.CTkScrollableFrame(container, label_text="Mock panel")
        left_wrap.pack(side="left", fill="both", expand=False, padx=(0, 10))
        self.mock = MockPropertiesPanel(left_wrap, self.params)
        self.mock.pack(fill="y", anchor="nw")

        # Right — controls
        self.controls = ControlsPanel(
            container, self.params, on_change=self._rebuild_mock,
        )
        self.controls.pack(side="right", fill="y")

    def _rebuild_mock(self) -> None:
        self.mock.configure(width=self.params["panel_width"])
        self.mock.rebuild()


if __name__ == "__main__":
    Playground().mainloop()
