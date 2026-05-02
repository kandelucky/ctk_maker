import sys
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from app.core.logger import log_error
from app.ui.crash_dialog import show_crash_dialog
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


def _install_crash_handlers(app: tk.Misc) -> None:
    """Route swallowed exceptions to the log file + crash dialog so
    shortcut launches (``pythonw.exe``, no console) still surface
    something readable. Two surfaces:

    - ``sys.excepthook`` — uncaught exceptions outside the Tk loop.
    - ``Tk.report_callback_exception`` — exceptions raised inside Tk
      callbacks (the common case once mainloop is running).
    """
    def _on_uncaught(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        tb_text = log_error("uncaught", exc_info=(exc_type, exc_value, exc_tb))
        show_crash_dialog(
            app, "CTk Maker — unexpected error",
            f"{exc_type.__name__}: {exc_value}",
            tb_text,
        )

    sys.excepthook = _on_uncaught

    def _on_tk_callback(self, *_args) -> None:  # noqa: ARG001
        exc_info = sys.exc_info()
        tb_text = log_error("tk_callback", exc_info=exc_info)
        summary = (
            f"{exc_info[0].__name__}: {exc_info[1]}"
            if exc_info[0] is not None else "Unexpected error"
        )
        show_crash_dialog(
            app, "CTk Maker — unexpected error", summary, tb_text,
        )

    type(app).report_callback_exception = _on_tk_callback


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
    _install_crash_handlers(app)
    app.mainloop()


if __name__ == "__main__":
    main()
