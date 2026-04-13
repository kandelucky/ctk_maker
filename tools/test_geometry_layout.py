"""
Isolated test for the Geometry group layout.

Edit the constants at the top and re-run to iterate.
Run from builder root:
    python tools/test_geometry_layout.py
"""
import tkinter as tk

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---- Tunable constants ------------------------------------------------------
PANEL_WIDTH = 200
PANEL_HEIGHT = 260
ROW_LABEL_WIDTH = 80
MINI_LABEL_WIDTH = 16
ENTRY_WIDTH = 52
HEADER_BG = "#2a2a2a"
VALUE_BG = "#2d2d2d"
VALUE_CORNER = 3
LABEL_FONT = ("", 10)
PANEL_CORNER = 0


class TestApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Geometry Layout (PANEL_WIDTH={PANEL_WIDTH})")
        w = PANEL_WIDTH + 40
        h = PANEL_HEIGHT + 40
        self.geometry(f"{w}x{h}+400+200")
        self.minsize(w, h)

        panel = ctk.CTkFrame(
            self, width=PANEL_WIDTH, height=PANEL_HEIGHT,
            corner_radius=PANEL_CORNER,
        )
        panel.pack(fill="both", expand=True, padx=20, pady=20)
        panel.pack_propagate(False)

        self._build_geometry_group(panel)

    def _build_geometry_group(self, parent):
        header = ctk.CTkFrame(parent, fg_color=HEADER_BG, height=22,
                              corner_radius=0)
        header.pack(fill="x", pady=(8, 2))
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="Geometry", fg_color=HEADER_BG,
                     font=("", 10, "bold"), text_color="#cccccc",
                     anchor="w").pack(side="left", padx=(20, 6))

        self._build_row(parent, "Position", [("X", 480), ("Y", 280)])
        self._build_row(parent, "Size", [("W", 140), ("H", 32)])

    def _build_row(self, parent, row_label_text, items):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2, padx=2)

        row.grid_columnconfigure(0, minsize=ROW_LABEL_WIDTH)
        row.grid_columnconfigure(1, weight=1)

        row_label = ctk.CTkLabel(
            row, text=row_label_text, anchor="w", font=LABEL_FONT,
        )
        row_label.grid(row=0, column=0, sticky="w", padx=(4, 0))

        col = 2
        for i, (text, value) in enumerate(items):
            row.grid_columnconfigure(col, minsize=MINI_LABEL_WIDTH)
            row.grid_columnconfigure(col + 1, minsize=ENTRY_WIDTH)

            label = ctk.CTkLabel(
                row, text=text, width=MINI_LABEL_WIDTH,
                anchor="e", font=LABEL_FONT,
            )
            label.grid(row=0, column=col, sticky="ew",
                       padx=(6 if i > 0 else 0, 2))

            entry = ctk.CTkEntry(
                row, width=ENTRY_WIDTH, height=22, font=LABEL_FONT,
                border_width=0, fg_color=VALUE_BG,
                corner_radius=VALUE_CORNER,
            )
            entry.insert(0, str(value))
            entry.grid(row=0, column=col + 1, sticky="ew")

            col += 2


if __name__ == "__main__":
    TestApp().mainloop()
