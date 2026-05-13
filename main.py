import sys
import tkinter as tk

import customtkinter as ctk

from app.core.logger import log_error
from app.ui.crash_dialog import show_crash_dialog
from app.ui.dark_titlebar import install_dark_titlebar_persistence
from app.ui.main_window import MainWindow


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
    install_dark_titlebar_persistence()
    app = MainWindow()
    _install_crash_handlers(app)
    app.mainloop()


if __name__ == "__main__":
    main()
