"""Quick palette demo — 10 tasteful accent colors for the CTkMaker
dark theme. Click a swatch to copy its hex to the clipboard, then
plug it in everywhere the current default blue (#1f6aa5) appears.

Picks are Tailwind 500-level — well-tuned for contrast on dark
backgrounds and easy to remember/share.
"""

from __future__ import annotations

import customtkinter as ctk

# (label, hex, hover_hex, fg_text_color)
PALETTE = [
    ("Indigo",   "#6366f1", "#4f46e5", "white"),
    ("Violet",   "#8b5cf6", "#7c3aed", "white"),
    ("Pink",     "#ec4899", "#db2777", "white"),
    ("Rose",     "#f43f5e", "#e11d48", "white"),
    ("Orange",   "#f97316", "#ea580c", "black"),
    ("Amber",    "#f59e0b", "#d97706", "black"),
    ("Lime",     "#84cc16", "#65a30d", "black"),
    ("Emerald",  "#10b981", "#059669", "white"),
    ("Teal",     "#14b8a6", "#0d9488", "white"),
    ("Cyan",     "#06b6d4", "#0891b2", "black"),
]

BG = "#1e1e1e"
PANEL = "#252526"
TITLE_FG = "#cccccc"
HINT_FG = "#888888"
SELECTED_RING = "#ffffff"


class ColorSwatchApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("CTkMaker — palette swatches")
        self.geometry("520x520")
        self.configure(fg_color=BG)

        ctk.CTkLabel(
            self, text="Click a swatch to copy its hex.",
            font=("Segoe UI", 12), text_color=TITLE_FG,
        ).pack(pady=(16, 4))
        self._status = ctk.CTkLabel(
            self, text="No swatch picked yet.",
            font=("Segoe UI", 10, "italic"), text_color=HINT_FG,
        )
        self._status.pack(pady=(0, 12))

        grid = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        grid.pack(fill="both", expand=True, padx=16, pady=8)

        cols = 2
        for index, (name, hex_color, hover, text_fg) in enumerate(PALETTE):
            row, col = divmod(index, cols)
            btn = ctk.CTkButton(
                grid,
                text=f"{name}   {hex_color}",
                fg_color=hex_color,
                hover_color=hover,
                text_color=text_fg,
                corner_radius=6,
                height=42,
                font=("Segoe UI", 12, "bold"),
                command=lambda h=hex_color, n=name: self._on_pick(n, h),
            )
            btn.grid(
                row=row, column=col, sticky="nsew", padx=6, pady=6,
            )

        for c in range(cols):
            grid.grid_columnconfigure(c, weight=1)
        for r in range((len(PALETTE) + cols - 1) // cols):
            grid.grid_rowconfigure(r, weight=1)

    def _on_pick(self, name: str, hex_color: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(hex_color)
            self.update()
        except Exception:
            pass
        self._status.configure(
            text=f"Copied → {name}   {hex_color}",
            text_color=hex_color,
        )


if __name__ == "__main__":
    ColorSwatchApp().mainloop()
