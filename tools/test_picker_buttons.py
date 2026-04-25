"""Stand-alone skeleton of the font-picker bottom row.

Used to debug why Reset / Cancel / Apply weren't landing where the
font picker's grid layout said they would. Three layout strategies
side-by-side so we can compare what Tk actually renders for each.
Pick the one that matches expectation, port it back into
``font_picker_dialog._build_footer``.

Run:
    python tools/test_picker_buttons.py
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

ctk.set_appearance_mode("dark")

root = ctk.CTk()
root.title("Picker buttons — layout test")
root.geometry("460x420")

# A: pack(side=) — what the picker had originally.
ctk.CTkLabel(root, text="A: pack(side=...)").pack(pady=(10, 2))
foot_a = tk.Frame(root, bg="#1e1e1e")
foot_a.pack(fill="x", padx=10, pady=(0, 12))
ctk.CTkButton(
    foot_a, text="Reset", width=70, height=32, corner_radius=10,
    fg_color="#3c3c3c", hover_color="#4a4a4a",
).pack(side="left")
ctk.CTkButton(
    foot_a, text="Apply", width=140, height=32, corner_radius=10,
).pack(side="right")
ctk.CTkButton(
    foot_a, text="Cancel", width=90, height=32, corner_radius=10,
    fg_color="#3c3c3c", hover_color="#4a4a4a",
).pack(side="right", padx=(0, 8))


# B: grid(...) — explicit columns.
ctk.CTkLabel(root, text="B: grid(...) with weight spacer").pack(pady=(10, 2))
foot_b = tk.Frame(root, bg="#1e1e1e")
foot_b.pack(fill="x", padx=10, pady=(0, 12))
foot_b.grid_columnconfigure(0, weight=0)
foot_b.grid_columnconfigure(1, weight=1)
foot_b.grid_columnconfigure(2, weight=0)
foot_b.grid_columnconfigure(3, weight=0)
ctk.CTkButton(
    foot_b, text="Reset", width=70, height=32, corner_radius=10,
    fg_color="#3c3c3c", hover_color="#4a4a4a",
).grid(row=0, column=0, sticky="w")
ctk.CTkButton(
    foot_b, text="Cancel", width=90, height=32, corner_radius=10,
    fg_color="#3c3c3c", hover_color="#4a4a4a",
).grid(row=0, column=2, padx=(0, 8))
ctk.CTkButton(
    foot_b, text="Apply", width=140, height=32, corner_radius=10,
).grid(row=0, column=3, sticky="e")


# C: place(...) — pixel-perfect, ignores any layout side-effects.
ctk.CTkLabel(root, text="C: place(x=...) absolute").pack(pady=(10, 2))
foot_c = tk.Frame(root, bg="#1e1e1e", height=44)
foot_c.pack(fill="x", padx=10, pady=(0, 12))
foot_c.pack_propagate(False)
ctk.CTkButton(
    foot_c, text="Reset", width=70, height=32, corner_radius=10,
    fg_color="#3c3c3c", hover_color="#4a4a4a",
).place(x=0, y=4)
ctk.CTkButton(
    foot_c, text="Cancel", width=90, height=32, corner_radius=10,
    fg_color="#3c3c3c", hover_color="#4a4a4a",
).place(relx=1.0, x=-(140 + 8 + 90), y=4)
ctk.CTkButton(
    foot_c, text="Apply", width=140, height=32, corner_radius=10,
).place(relx=1.0, x=-140, y=4)


# D: same as B but with ``.update_idletasks()`` printing widths so we
# see what Tk actually allocated.
ctk.CTkLabel(root, text="D: grid + width report").pack(pady=(10, 2))
foot_d = tk.Frame(root, bg="#1e1e1e")
foot_d.pack(fill="x", padx=10, pady=(0, 4))
foot_d.grid_columnconfigure(0, weight=0)
foot_d.grid_columnconfigure(1, weight=1)
foot_d.grid_columnconfigure(2, weight=0)
foot_d.grid_columnconfigure(3, weight=0)
b_reset = ctk.CTkButton(
    foot_d, text="Reset", width=70, height=32, corner_radius=10,
    fg_color="#3c3c3c", hover_color="#4a4a4a",
)
b_reset.grid(row=0, column=0, sticky="w")
b_cancel = ctk.CTkButton(
    foot_d, text="Cancel", width=90, height=32, corner_radius=10,
    fg_color="#3c3c3c", hover_color="#4a4a4a",
)
b_cancel.grid(row=0, column=2, padx=(0, 8))
b_apply = ctk.CTkButton(
    foot_d, text="Apply", width=140, height=32, corner_radius=10,
)
b_apply.grid(row=0, column=3, sticky="e")

report = tk.Label(
    root, bg="#1e1e1e", fg="#cccccc", font=("Consolas", 9),
    anchor="w", justify="left",
)
report.pack(fill="x", padx=10, pady=(0, 8))


def _report() -> None:
    root.update_idletasks()
    parts = []
    for name, b in (
        ("Reset", b_reset), ("Cancel", b_cancel), ("Apply", b_apply),
    ):
        parts.append(
            f"{name}: declared={b.cget('width')} "
            f"actual={b.winfo_width()} x={b.winfo_x()}"
        )
    report.configure(text="\n".join(parts))


root.after(200, _report)
root.mainloop()
