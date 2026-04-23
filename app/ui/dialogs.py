"""Modal dialogs used by the builder.

NewProjectSizeDialog (File → New): standalone modal wrapping
NewProjectForm. Returns (name, path, w, h) on Create or None if
the user cancels.

RenameDialog: blocking single-line rename modal used by the workspace
right-click menu and the Object Tree right-click menu.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog

import customtkinter as ctk

from app.ui.new_project_form import NewProjectForm


class RenameDialog(simpledialog.Dialog):
    """Blocking rename dialog. Rejects empty names: bells, restores the
    original value in the entry, and keeps the dialog open.
    """

    def __init__(self, parent, initial_value: str):
        self._initial = initial_value
        self.result: str | None = None
        super().__init__(parent, "Rename Widget")

    def body(self, master):
        tk.Label(master, text="New name:").pack(padx=16, pady=(12, 4))
        self.entry = tk.Entry(master, width=30)
        self.entry.insert(0, self._initial)
        self.entry.select_range(0, tk.END)
        self.entry.pack(padx=16, pady=(0, 12))
        return self.entry

    def validate(self) -> bool:
        value = self.entry.get().strip()
        if not value:
            self.bell()
            self.entry.delete(0, tk.END)
            self.entry.insert(0, self._initial)
            self.entry.select_range(0, tk.END)
            self.entry.focus_set()
            return False
        self.result = value
        return True

    def apply(self):
        # result is already set inside validate()
        pass


DIALOG_PRESETS: list[tuple[str, tuple[int, int] | None]] = [
    ("Same as Main", None),       # resolves to main_w × main_h at init
    ("Alert — 380 × 160", (380, 160)),
    ("Compact — 420 × 280", (420, 280)),
    ("Medium — 520 × 380", (520, 380)),
    ("Settings — 640 × 480", (640, 480)),
    ("Wizard — 720 × 520", (720, 520)),
    ("Custom", None),             # user edits W/H directly
]


class AddDialogSizeDialog(ctk.CTkToplevel):
    """Quick modal for the Form → Add Dialog flow. Asks for a
    name + width + height and returns ``(name, w, h)`` on OK, or
    ``None`` on Cancel. Unlike NewProjectSizeDialog there's no
    save path — the dialog lives inside the current project.
    Includes a preset dropdown with standard sizes so users don't
    have to guess common dimensions.
    """

    def __init__(
        self,
        parent,
        default_name: str = "Dialog",
        main_w: int = 800,
        main_h: int = 600,
    ):
        super().__init__(parent)
        self.title("Add dialog")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: tuple[str, int, int] | None = None
        self._main_w = int(main_w)
        self._main_h = int(main_h)
        self._suspend_preset_sync = False

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=20, pady=(18, 10), fill="x")

        ctk.CTkLabel(body, text="Name").grid(
            row=0, column=0, sticky="w", pady=(0, 4),
        )
        self._name_var = tk.StringVar(value=default_name)
        name_entry = ctk.CTkEntry(
            body, textvariable=self._name_var, width=220,
        )
        name_entry.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10),
        )

        ctk.CTkLabel(body, text="Size Preset").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 4),
        )
        self._preset_var = tk.StringVar(value=DIALOG_PRESETS[0][0])
        preset_menu = ctk.CTkOptionMenu(
            body,
            values=[label for label, _ in DIALOG_PRESETS],
            variable=self._preset_var,
            width=220,
            command=self._on_preset_change,
        )
        preset_menu.grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(0, 12),
        )

        ctk.CTkLabel(body, text="Width").grid(
            row=4, column=0, sticky="w", pady=(0, 4),
        )
        ctk.CTkLabel(body, text="Height").grid(
            row=4, column=1, sticky="w", pady=(0, 4), padx=(8, 0),
        )
        self._w_var = tk.StringVar(value=str(main_w))
        self._h_var = tk.StringVar(value=str(main_h))
        self._w_var.trace_add("write", self._on_size_edited)
        self._h_var.trace_add("write", self._on_size_edited)
        ctk.CTkEntry(body, textvariable=self._w_var, width=106).grid(
            row=5, column=0, sticky="w",
        )
        ctk.CTkEntry(body, textvariable=self._h_var, width=106).grid(
            row=5, column=1, sticky="w", padx=(8, 0),
        )
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(
            footer, text="Add", width=120, height=32,
            corner_radius=4, command=self._on_ok,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        name_entry.focus_set()
        name_entry.select_range(0, tk.END)
        self.after(100, self._center_on_parent)

    def _on_preset_change(self, label: str) -> None:
        for name, size in DIALOG_PRESETS:
            if name != label:
                continue
            if name == "Same as Main":
                w, h = self._main_w, self._main_h
            elif name == "Custom":
                return  # keep the current W/H for editing
            elif size is not None:
                w, h = size
            else:
                return
            self._suspend_preset_sync = True
            try:
                self._w_var.set(str(w))
                self._h_var.set(str(h))
            finally:
                self._suspend_preset_sync = False
            break

    def _on_size_edited(self, *_args) -> None:
        # Typing into W/H manually → flip the preset to "Custom" so
        # the dropdown doesn't lie about the currently-shown size.
        if self._suspend_preset_sync:
            return
        if self._preset_var.get() != "Custom":
            self._preset_var.set("Custom")

    # Match New Project clamp range — anything outside this gets
    # bounced with a bell so the dialog can't ship absurd sizes
    # (huge negatives crash tk; 4-digit numbers above 4000 exceed any
    # real screen and silently break the preview launch).
    _SIZE_MIN = 100
    _SIZE_MAX = 4000

    def _on_ok(self) -> None:
        from tkinter import messagebox
        name = self._name_var.get().strip()
        if not name:
            self.bell()
            return
        try:
            w = int(self._w_var.get())
            h = int(self._h_var.get())
        except ValueError:
            self.bell()
            messagebox.showwarning(
                "Invalid size",
                f"Width and height must be whole numbers "
                f"between {self._SIZE_MIN} and {self._SIZE_MAX}.",
                parent=self,
            )
            return
        if not (
            self._SIZE_MIN <= w <= self._SIZE_MAX
            and self._SIZE_MIN <= h <= self._SIZE_MAX
        ):
            self.bell()
            messagebox.showwarning(
                "Size out of range",
                f"Dialog width and height must be between "
                f"{self._SIZE_MIN} and {self._SIZE_MAX} pixels.",
                parent=self,
            )
            return
        self.result = (name, w, h)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")


class NewProjectSizeDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        default_w: int = 800,
        default_h: int = 600,
        default_name: str = "Untitled",
        default_save_dir: str | None = None,
    ):
        super().__init__(parent)
        self.title("New project")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: tuple[str, str, int, int] | None = None

        self._form = NewProjectForm(
            self,
            default_w=default_w,
            default_h=default_h,
            default_name=default_name,
            default_save_dir=default_save_dir,
        )
        self._form.pack(padx=20, pady=(20, 10), fill="both", expand=True)

        self._build_footer()

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.after(100, self._center_on_parent)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(
            footer, text="+ Create Project", width=160, height=32,
            corner_radius=4, command=self._on_ok,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _on_ok(self) -> None:
        validated = self._form.validate_and_get()
        if validated is None:
            return
        self.result = validated
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


# ---------------------------------------------------------------------------
# About dialog
# ---------------------------------------------------------------------------

_BUILT_WITH = [
    ("CustomTkinter",         "https://github.com/TomSchimansky/CustomTkinter", "MIT"),
    ("Lucide Icons",          "https://lucide.dev",                              "MIT"),
    ("Pillow",                "https://pypi.org/project/Pillow/",                "HPND"),
    ("ctk-tint-color-picker", "https://pypi.org/project/ctk-tint-color-picker/", "MIT"),
]

_ABT_BG   = "#1e1e1e"
_ABT_FG   = "#cccccc"
_ABT_DIM  = "#888888"
_ABT_LINK = "#5bc0f8"
_ABT_SEP  = "#3a3a3a"


class AboutDialog(tk.Toplevel):
    def __init__(self, parent, app_version: str = ""):
        super().__init__(parent)
        self.title("About CTk Visual Builder")
        self.configure(bg=_ABT_BG)
        self.resizable(False, False)
        self.transient(parent)
        self._build(app_version)
        # Fixed size — position centered on parent
        W, H = 480, 320
        px = parent.winfo_rootx() + parent.winfo_width() // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"{W}x{H}+{px - W // 2}+{py - H // 2}")
        self.lift()
        self.focus_set()

    def _build(self, version: str) -> None:
        import webbrowser
        pad = dict(padx=24)

        tk.Frame(self, bg=_ABT_BG, height=20).pack()
        tk.Label(
            self, text="CTk Visual Builder",
            bg=_ABT_BG, fg=_ABT_FG, font=("Segoe UI", 16, "bold"),
        ).pack(**pad)
        tk.Label(
            self, text=version or "",
            bg=_ABT_BG, fg=_ABT_DIM, font=("Segoe UI", 10),
        ).pack(**pad, pady=(2, 0))
        tk.Label(
            self,
            text="Drag-and-drop designer for CustomTkinter\nthat exports clean Python code.",
            bg=_ABT_BG, fg=_ABT_DIM, font=("Segoe UI", 10), justify="center",
        ).pack(padx=24, pady=(12, 0))

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(fill="x", padx=24, pady=16)

        tk.Label(
            self, text="Built with",
            bg=_ABT_BG, fg=_ABT_FG, font=("Segoe UI", 10, "bold"),
        ).pack(**pad, pady=(0, 8))

        for name, url, lic in _BUILT_WITH:
            row = tk.Frame(self, bg=_ABT_BG)
            row.pack(fill="x", padx=24, pady=2)
            tk.Label(
                row, text=f"{name}  ", bg=_ABT_BG, fg=_ABT_FG,
                font=("Segoe UI", 10), anchor="w",
            ).pack(side="left")
            link = tk.Label(
                row, text=url, bg=_ABT_BG, fg=_ABT_LINK,
                font=("Segoe UI", 10, "underline"), cursor="hand2",
            )
            link.pack(side="left")
            link.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
            tk.Label(
                row, text=f"  ({lic})", bg=_ABT_BG, fg=_ABT_DIM,
                font=("Segoe UI", 9),
            ).pack(side="left")

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(fill="x", padx=24, pady=16)
        btn = tk.Button(
            self, text="Close", command=self.destroy,
            bg="#3a3a3a", fg=_ABT_FG, activebackground="#4a4a4a",
            activeforeground=_ABT_FG, relief="flat", bd=0,
            font=("Segoe UI", 10), padx=20, pady=4, cursor="hand2",
        )
        btn.pack(pady=(0, 20))
