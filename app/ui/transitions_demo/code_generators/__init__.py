"""Per-tab "Generate code" snippet builders.

Each ``generate_<tab>_code`` is a pure function: takes the current
Easing / Duration (plus tab-specific args) and returns a self-contained
Python module string the user can paste anywhere — no import back
into CTkMaker. ``base`` holds the shared HSL helper, Tween block, and
the ``assemble_module`` stitcher used by every tab except Button
(Button has a bespoke callable-wrapping template).
"""

from app.ui.transitions_demo.code_generators.base import (
    HSL_HELPER, TWEEN_BLOCK, assemble_module,
)
from app.ui.transitions_demo.code_generators.button import generate_button_code
from app.ui.transitions_demo.code_generators.card import generate_card_code
from app.ui.transitions_demo.code_generators.loaders import generate_loader_code
from app.ui.transitions_demo.code_generators.popups import generate_popup_code
from app.ui.transitions_demo.code_generators.text import generate_text_code
from app.ui.transitions_demo.code_generators.toasts import generate_toast_code

__all__ = [
    "HSL_HELPER",
    "TWEEN_BLOCK",
    "assemble_module",
    "generate_button_code",
    "generate_card_code",
    "generate_loader_code",
    "generate_popup_code",
    "generate_text_code",
    "generate_toast_code",
]
