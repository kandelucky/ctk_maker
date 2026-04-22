"""Print the real `__init__` signature of any CTk widget.

Source of truth for widget kwargs — the official CustomTkinter doc
site at customtkinter.tomschimansky.com is incomplete (missed
`checkmark_color` and `bg_color` on CTkCheckBox at the time of
writing). This script reads the actual installed `customtkinter`
package via `inspect.signature(...)` so what you see is what your
code will actually accept at runtime.

Usage:
    python tools/inspect_ctk_widget.py CTkButton
    python tools/inspect_ctk_widget.py CTkCheckBox
    python tools/inspect_ctk_widget.py CTkEntry CTkTextbox
    python tools/inspect_ctk_widget.py            # lists every widget

Tip: pipe to clip on Windows to compare against a descriptor:
    python tools/inspect_ctk_widget.py CTkSlider | clip
"""

from __future__ import annotations

import inspect
import sys

import customtkinter as ctk

# Windows console default encoding is cp1252; force UTF-8 so ANSI
# colour escapes and any unicode in annotations don't crash with
# UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


# ANSI colour codes — Windows 10+ Terminal, VSCode, modern shells handle these.
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
GREY = "\033[90m"
RED = "\033[31m"


def _all_widget_class_names() -> list[str]:
    return sorted(
        name for name in dir(ctk)
        if name.startswith("CTk")
        and inspect.isclass(getattr(ctk, name))
    )


def _print_signature(class_name: str) -> None:
    cls = getattr(ctk, class_name, None)
    if cls is None or not inspect.isclass(cls):
        print(f"{RED}? {class_name} not found in customtkinter{RESET}")
        return

    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError) as exc:
        print(f"{RED}? {class_name} signature unavailable: {exc}{RESET}")
        return

    print()
    print(f"{BOLD}{CYAN}{class_name}{RESET}  "
          f"{DIM}({cls.__module__}){RESET}")
    print(f"{GREY}{'─' * 60}{RESET}")

    params = list(sig.parameters.values())
    name_w = max(
        (len(p.name) for p in params if p.name not in ("self", "kwargs")),
        default=10,
    )

    for p in params:
        if p.name == "self":
            continue
        if p.name == "kwargs":
            print(f"  {DIM}**{p.name}{RESET}")
            continue

        default_repr = (
            f"{YELLOW}{p.default!r}{RESET}"
            if p.default is not inspect._empty else f"{RED}<required>{RESET}"
        )
        anno = ""
        if p.annotation is not inspect._empty:
            anno_str = (
                str(p.annotation)
                .replace("typing.", "")
                .replace("customtkinter.windows.widgets.", "")
            )
            anno = f"  {DIM}{anno_str}{RESET}"
        print(f"  {GREEN}{p.name:<{name_w}}{RESET} "
              f"= {default_repr}{anno}")

    print()


def main(argv: list[str]) -> int:
    if not argv:
        print(f"{BOLD}Available CTk widgets:{RESET}")
        for name in _all_widget_class_names():
            print(f"  {CYAN}{name}{RESET}")
        print()
        print(f"{DIM}Usage: python tools/inspect_ctk_widget.py "
              f"<ClassName> [<ClassName> ...]{RESET}")
        return 0

    for class_name in argv:
        _print_signature(class_name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
