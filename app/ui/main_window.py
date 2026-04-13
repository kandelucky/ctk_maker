import tkinter as tk

import customtkinter as ctk

from app.core.project import Project
from app.ui.palette import Palette
from app.ui.properties_panel import PropertiesPanel
from app.ui.workspace import Workspace


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CTk Visual Builder")
        self.minsize(900, 600)
        self._set_centered_geometry(1280, 800)

        self.project = Project()

        self.paned = tk.PanedWindow(
            self,
            orient=tk.HORIZONTAL,
            sashwidth=5,
            sashrelief=tk.FLAT,
            bg="#1e1e1e",
            borderwidth=0,
            showhandle=False,
        )
        self.paned.pack(fill="both", expand=True, padx=8, pady=8)

        self.palette = Palette(self.paned, self.project)
        self.workspace = Workspace(self.paned, self.project)
        self.properties = PropertiesPanel(self.paned, self.project)

        self.paned.add(self.palette, minsize=150, width=200, stretch="never")
        self.paned.add(self.workspace, minsize=400, stretch="always")
        self.paned.add(self.properties, minsize=320, width=340, stretch="never")

    def _set_centered_geometry(self, desired_w: int, desired_h: int) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(desired_w, sw - 80)
        h = min(desired_h, sh - 120)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")
