"""CTkMaker — Visual UI designer for CustomTkinter.

This package reserves the PyPI name. The full builder lives in
``app/`` of the source tree and launches via ``python main.py``.

See: https://github.com/kandelucky/ctk_maker
"""

__version__ = "1.66.0"


def main() -> None:
    print(
        f"CTkMaker v{__version__}\n"
        "This PyPI package reserves the name — the builder itself runs "
        "from the source tree:\n"
        "  git clone https://github.com/kandelucky/ctk_maker.git\n"
        "  cd ctk_maker\n"
        "  pip install -r requirements.txt\n"
        "  python main.py\n"
        "Docs: https://github.com/kandelucky/ctk_maker/wiki\n"
        "Releases: https://github.com/kandelucky/ctk_maker/releases"
    )


if __name__ == "__main__":
    main()
