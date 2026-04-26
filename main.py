import sys
from pathlib import Path

import customtkinter as ctk

from app.ui.main_window import MainWindow

ICON_ICO = Path(__file__).resolve().parent / "app" / "assets" / "icon.ico"


def _patch_ctk_toplevel_icon() -> None:
    """Make every ``CTkToplevel`` adopt the app icon.

    ``iconbitmap(default=...)`` on the root only propagates onto bare
    ``tk.Toplevel`` children. ``CTkToplevel`` runs its own
    Windows-specific ``after`` setup that overwrites the inherited icon
    with a transparent placeholder, so dialogs end up with the default
    Tk feather. Re-apply our icon ~250 ms after each Toplevel is built
    — that's well after CTk's own scheduled handler.
    """
    if sys.platform != "win32" or not ICON_ICO.exists():
        return
    icon_path = str(ICON_ICO)
    orig_init = ctk.CTkToplevel.__init__

    def _patched_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        try:
            self.after(250, lambda: self.iconbitmap(icon_path))
        except Exception:
            pass

    ctk.CTkToplevel.__init__ = _patched_init


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    # Force a Unicode-complete default font so non-Latin scripts
    # render instead of falling back to "?". CTk defaults to Roboto on
    # Windows, which lacks coverage for many non-Latin scripts.
    if sys.platform == "win32":
        ctk.ThemeManager.theme["CTkFont"]["family"] = "Segoe UI"
    _patch_ctk_toplevel_icon()
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
