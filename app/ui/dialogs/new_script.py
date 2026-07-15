"""New-script prompt — a ``RenameDialog`` that normalizes any input
style to a PascalCase class name and previews the result live.

The user types whatever comes naturally (``foo bar``,
``foo_bar``, ``FooBar``); the dialog shows the class + file
that will be created and only asks them to confirm. OK is refused (bell,
dialog stays open) while the name is invalid or the class already exists
in ``scripts/`` — a duplicate class name would collide in the attach
picker, which filters attached scripts by class name alone.
"""

from __future__ import annotations

from app.io.scripts import class_name_to_filename, normalize_class_name
from app.ui import style
from app.ui.dialogs.rename import RenameDialog

_PREVIEW_FG = "#999999"
_PROBLEM_FG = "#ff8080"


class NewScriptDialog(RenameDialog):
    """Blocking prompt for a new CTkScript. ``result`` is the
    **normalized** class name (or ``None`` on cancel). ``existing`` maps
    class name → rel path for every attachable class in ``scripts/``.
    """

    default_size = (360, 200)
    min_size = (340, 200)

    def __init__(self, parent, existing: dict[str, str]):
        self._existing = existing
        super().__init__(
            parent, "",
            title="New script",
            label="Script name (e.g. login form):",
            validate=self._accepts,
        )

    def _build_extra(self, body) -> None:
        self._preview = style.styled_label(body, "")
        self._preview.configure(text_color=_PREVIEW_FG, anchor="w")
        self._preview.pack(fill="x", pady=(6, 0))
        self._name_var.trace_add(
            "write", lambda *_a: self._update_preview(),
        )

    def _update_preview(self) -> None:
        raw = self._name_var.get().strip()
        cls = normalize_class_name(raw)
        if not raw:
            text, color = "", _PREVIEW_FG
        elif not cls:
            text, color = "Not a usable name", _PROBLEM_FG
        elif cls in self._existing:
            text = f"{cls} already exists ({self._existing[cls]})"
            color = _PROBLEM_FG
        else:
            text = f"class {cls}   —   {class_name_to_filename(cls)}.py"
            color = _PREVIEW_FG
        self._preview.configure(text=text, text_color=color)

    def _accepts(self, raw: str) -> bool:
        cls = normalize_class_name(raw)
        return bool(cls) and cls not in self._existing

    def _on_ok(self) -> None:
        super()._on_ok()
        if self.result is not None:
            self.result = normalize_class_name(self.result)
