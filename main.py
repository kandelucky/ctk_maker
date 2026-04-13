import sys

import customtkinter as ctk

from app.ui.main_window import MainWindow


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    # Force a Unicode-complete default font so non-Latin scripts
    # (Georgian, Cyrillic, Greek, ...) render instead of falling back
    # to `?`. CTk defaults to Roboto on Windows, which lacks Georgian.
    if sys.platform == "win32":
        ctk.ThemeManager.theme["CTkFont"]["family"] = "Segoe UI"
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
