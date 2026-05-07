"""Phase 2 Step 3 — modal confirmation dialogs for the two destructive
operations on visual-scripting state:

- ``WindowDeleteDialog`` — runs before removing a Document. Surfaces
  the window's contents (widgets / locals / behavior-script line
  count) and lets the user route the script either to the OS recycle
  bin (default, recoverable via Windows / macOS / Linux trash) or to
  ``<project>/assets/scripts_archive/<page>/<window>.py`` (with auto
  ``_2`` / ``_3`` suffix on collision). The active scripts folder
  always ends up clean either way.
- ``ActionDeleteDialog`` — runs before unbinding + deleting a
  handler method. Three buttons: Cancel, Open in editor (so the
  user can copy the body before clicking Delete again), Delete.

Both dialogs return their decision via instance attributes the
caller reads after ``wait_window``.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from app.ui.dialog_utils import prepare_dialog, reveal_dialog, safe_grab_set

_BG = "#1a1a1a"
_HEADING_FG = "#e6e6e6"
_BODY_FG = "#bdbdbd"
_CARD_BG = "#252526"
_BTN_BG = "#3c3c3c"
_BTN_HOVER = "#4a4a4a"
_DANGER_BG = "#a23a3a"
_DANGER_HOVER = "#bf4646"
_LINK_FG = "#5eb3ff"


def _center_on_parent(dialog: ctk.CTkToplevel) -> None:
    dialog.update_idletasks()
    parent = dialog.master
    try:
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
    except tk.TclError:
        reveal_dialog(dialog)
        return
    w = dialog.winfo_width()
    h = dialog.winfo_height()
    x = px + (pw - w) // 2
    y = py + (ph - h) // 2
    dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
    reveal_dialog(dialog)


class WindowDeleteDialog(ctk.CTkToplevel):
    """Confirmation gate for ``DeleteDocumentCommand``. Shown for
    every window deletion regardless of what the window contains —
    the user always knows what's about to disappear, even for empty
    forms (no surprise loss of an in-progress dialog).

    On ``[Delete window]`` the caller reads:
    - ``self.confirmed`` — True only when Delete was clicked.
    - ``self.script_action`` — ``"recycle"`` / ``"save"`` / ``"none"``.
      ``"none"`` means there's no behavior file to dispose of.
    - ``self.save_target_path`` — populated when ``script_action ==
      "save"``; the absolute path the caller will move the .py to.

    The Save Copy default lands inside the same project at
    ``<project>/assets/scripts_archive/<page>/<window>.py`` so the
    user never accidentally scatters .py backups across the
    filesystem (per the project's "scripts folder = active code
    only" principle).
    """

    def __init__(
        self,
        parent,
        window_name: str,
        widget_count: int,
        local_var_count: int,
        method_count: int,
        line_count: int,
        default_save_path: str | Path,
    ):
        super().__init__(parent)
        prepare_dialog(self)
        self.title("Delete window")
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)
        self.configure(fg_color=_BG)

        self.confirmed: bool = False
        self.script_action: str = (
            "recycle" if method_count > 0 else "none"
        )
        self.save_target_path: str = str(default_save_path)
        self._has_script = method_count > 0

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=22, pady=(20, 8), fill="x")

        ctk.CTkLabel(
            body, text=f"Delete \"{window_name}\"?",
            font=("Segoe UI", 14, "bold"),
            text_color=_HEADING_FG, anchor="w",
        ).pack(anchor="w", pady=(0, 10))

        # Contents card — always shown so empty windows surface the
        # zero counts (the user explicitly asked for "always know
        # what gets deleted").
        info = ctk.CTkFrame(
            body, fg_color=_CARD_BG, corner_radius=4,
        )
        info.pack(fill="x", pady=(0, 12))
        bullets: list[str] = [
            f"• {widget_count} widget{'s' if widget_count != 1 else ''}",
            f"• {local_var_count} local variable"
            f"{'s' if local_var_count != 1 else ''} "
            "(will be lost)",
        ]
        if method_count > 0:
            bullets.append(
                f"• Behavior script — {method_count} method"
                f"{'s' if method_count != 1 else ''}, "
                f"{line_count} line"
                f"{'s' if line_count != 1 else ''}",
            )
        else:
            bullets.append("• No behavior script attached")
        ctk.CTkLabel(
            info, text="\n".join(bullets),
            font=("Segoe UI", 10),
            text_color=_BODY_FG,
            justify="left", anchor="w", wraplength=420,
        ).pack(anchor="w", padx=12, pady=10)

        if self._has_script:
            ctk.CTkLabel(
                body, text="Behavior script:",
                font=("Segoe UI", 10, "bold"),
                text_color=_HEADING_FG, anchor="w",
            ).pack(anchor="w", pady=(0, 4))

            self._script_action_var = tk.StringVar(value="recycle")

            recycle_row = tk.Frame(body, bg=_BG)
            recycle_row.pack(fill="x", pady=(2, 4))
            ctk.CTkRadioButton(
                recycle_row, text="Move to Recycle Bin",
                variable=self._script_action_var, value="recycle",
                command=self._on_action_radio,
                fg_color=_LINK_FG, hover_color=_LINK_FG,
                text_color=_BODY_FG,
            ).pack(side="left")
            ctk.CTkLabel(
                recycle_row,
                text="(recoverable from your OS trash)",
                font=("Segoe UI", 9),
                text_color="#888888", anchor="w",
            ).pack(side="left", padx=(8, 0))

            save_row = tk.Frame(body, bg=_BG)
            save_row.pack(fill="x", pady=(2, 0))
            ctk.CTkRadioButton(
                save_row, text="Save copy to:",
                variable=self._script_action_var, value="save",
                command=self._on_action_radio,
                fg_color=_LINK_FG, hover_color=_LINK_FG,
                text_color=_BODY_FG,
            ).pack(side="left")

            path_row = tk.Frame(body, bg=_BG)
            path_row.pack(fill="x", padx=(24, 0), pady=(4, 0))
            self._path_var = tk.StringVar(value=str(default_save_path))
            self._path_entry = ctk.CTkEntry(
                path_row,
                textvariable=self._path_var,
                width=320, height=28,
                state="disabled",
            )
            self._path_entry.pack(side="left", padx=(0, 6))
            self._browse_btn = ctk.CTkButton(
                path_row, text="Browse…",
                width=80, height=28, corner_radius=4,
                fg_color=_BTN_BG, hover_color=_BTN_HOVER,
                command=self._on_browse,
                state="disabled",
            )
            self._browse_btn.pack(side="left")

            ctk.CTkLabel(
                body,
                text=(
                    "An existing file at the target path keeps the "
                    "original — the new copy gets a _2 / _3 suffix."
                ),
                font=("Segoe UI", 9),
                text_color="#888888",
                anchor="w", justify="left", wraplength=420,
            ).pack(anchor="w", padx=(24, 0), pady=(6, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(16, 16))
        ctk.CTkButton(
            footer, text="Delete window",
            width=140, height=34, corner_radius=4,
            fg_color=_DANGER_BG, hover_color=_DANGER_HOVER,
            command=self._on_delete,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel",
            width=90, height=34, corner_radius=4,
            fg_color=_BTN_BG, hover_color=_BTN_HOVER,
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, lambda: _center_on_parent(self))

    def _on_action_radio(self) -> None:
        choice = self._script_action_var.get()
        new_state = "normal" if choice == "save" else "disabled"
        self._path_entry.configure(state=new_state)
        self._browse_btn.configure(state=new_state)

    def _on_browse(self) -> None:
        from tkinter import filedialog
        current = self._path_var.get().strip()
        initial_dir = (
            str(Path(current).parent) if current else str(Path.home())
        )
        initial_file = (
            Path(current).name if current else "behavior.py"
        )
        chosen = filedialog.asksaveasfilename(
            parent=self,
            title="Save behavior script copy",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=".py",
            filetypes=[("Python", "*.py"), ("All files", "*.*")],
        )
        if chosen:
            self._path_var.set(chosen)

    def _on_delete(self) -> None:
        self.confirmed = True
        if self._has_script:
            self.script_action = self._script_action_var.get()
            if self.script_action == "save":
                self.save_target_path = self._path_var.get().strip()
        self.destroy()

    def _on_cancel(self) -> None:
        self.confirmed = False
        self.destroy()


class ActionDeleteDialog(ctk.CTkToplevel):
    """Confirmation gate for the Properties panel ``[✕]`` button
    and the right-click ``Delete action`` entry. Three terminal
    buttons (no radios — every option is a one-click action):

    - **Cancel** — abandon the delete.
    - **Open in editor** — launch the user's editor at the method
      so they can copy the body before re-clicking ``[✕]``. Sets
      ``self.action = "open_editor"``; the dialog closes and the
      caller fires the editor-launch path.
    - **Delete** — confirms ``self.action = "delete"``; the caller
      removes the binding from the model AND deletes the ``def``
      from the .py file via the text-based helper.
    """

    def __init__(
        self,
        parent,
        method_name: str,
        line_count: int,
        also_bound_elsewhere: int = 0,
    ):
        super().__init__(parent)
        prepare_dialog(self)
        self.title("Delete action")
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)
        self.configure(fg_color=_BG)

        self.action: str = "cancel"

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=22, pady=(20, 8), fill="x")

        ctk.CTkLabel(
            body,
            text=f"Delete action \"{method_name}\"?",
            font=("Segoe UI", 13, "bold"),
            text_color=_HEADING_FG, anchor="w",
        ).pack(anchor="w", pady=(0, 8))

        info = ctk.CTkFrame(body, fg_color=_CARD_BG, corner_radius=4)
        info.pack(fill="x", pady=(0, 4))
        body_text = (
            f"This will remove the binding AND delete the method "
            f"from the behavior file ({line_count} line"
            f"{'s' if line_count != 1 else ''} of code).\n"
            f"Choose \"Open in editor\" first if you want to copy "
            f"the body before deleting."
        )
        ctk.CTkLabel(
            info, text=body_text,
            font=("Segoe UI", 10),
            text_color=_BODY_FG,
            justify="left", anchor="w", wraplength=420,
        ).pack(anchor="w", padx=12, pady=10)

        if also_bound_elsewhere > 0:
            warn = ctk.CTkFrame(
                body, fg_color="#3a2a18", corner_radius=4,
            )
            warn.pack(fill="x", pady=(8, 0))
            ctk.CTkLabel(
                warn,
                text=(
                    f"⚠  This method is also bound to "
                    f"{also_bound_elsewhere} other event"
                    f"{'s' if also_bound_elsewhere != 1 else ''} on "
                    "this window. Deleting the file definition will "
                    "break those too."
                ),
                font=("Segoe UI", 10),
                text_color="#e8a45e",
                justify="left", anchor="w", wraplength=420,
            ).pack(anchor="w", padx=12, pady=10)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(16, 16))
        ctk.CTkButton(
            footer, text="Delete",
            width=110, height=34, corner_radius=4,
            fg_color=_DANGER_BG, hover_color=_DANGER_HOVER,
            command=self._on_delete,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Open in editor",
            width=130, height=34, corner_radius=4,
            fg_color=_BTN_BG, hover_color=_BTN_HOVER,
            command=self._on_open_editor,
        ).pack(side="right", padx=(0, 8))
        ctk.CTkButton(
            footer, text="Cancel",
            width=90, height=34, corner_radius=4,
            fg_color=_BTN_BG, hover_color=_BTN_HOVER,
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, lambda: _center_on_parent(self))

    def _on_delete(self) -> None:
        self.action = "delete"
        self.destroy()

    def _on_open_editor(self) -> None:
        self.action = "open_editor"
        self.destroy()

    def _on_cancel(self) -> None:
        self.action = "cancel"
        self.destroy()


# ---------------------------------------------------------------------
# Orchestration helpers — keep call sites tiny
# ---------------------------------------------------------------------
def run_window_delete_flow(parent, project, doc) -> bool:
    """One-stop orchestrator: pop ``WindowDeleteDialog``, then route
    the behavior file per user choice. Returns ``True`` when the
    caller should proceed with the actual ``DeleteDocumentCommand``,
    ``False`` on Cancel.

    Counts the script's method + line totals up-front so the dialog
    can show them. When the project is unsaved or the file is
    missing the script section degrades to "no behavior script
    attached" inside the dialog body.
    """
    widget_count = _count_widgets_under(doc)
    local_var_count = len(getattr(doc, "local_variables", []) or [])
    method_count, line_count = _count_methods_for_doc(project, doc)
    default_save = _default_archive_target(project, doc)
    dialog = WindowDeleteDialog(
        parent,
        window_name=doc.name,
        widget_count=widget_count,
        local_var_count=local_var_count,
        method_count=method_count,
        line_count=line_count,
        default_save_path=default_save,
    )
    parent.wait_window(dialog)
    if not dialog.confirmed:
        return False
    if dialog.script_action == "recycle":
        try:
            from app.io.scripts import recycle_behavior_file
            recycle_behavior_file(project.path, doc.name)
        except OSError:
            pass
    elif dialog.script_action == "save":
        target = dialog.save_target_path
        if target:
            try:
                from app.io.scripts import save_behavior_file_copy
                save_behavior_file_copy(
                    project.path, doc.name, target,
                )
            except OSError:
                pass
    return True


def _count_widgets_under(doc) -> int:
    total = 0
    stack = list(doc.root_widgets)
    while stack:
        node = stack.pop()
        total += 1
        stack.extend(node.children)
    return total


def _count_methods_for_doc(project, doc) -> tuple[int, int]:
    """Return ``(method_count, line_count)`` for ``doc``'s behavior
    file. Both zero when the project is unsaved or the file isn't
    there yet — those cases collapse to "no behavior script
    attached" in the dialog body.
    """
    if not getattr(project, "path", None):
        return (0, 0)
    try:
        from app.core.script_paths import (
            behavior_class_name, behavior_file_path,
        )
        from app.io.scripts import parse_handler_methods
    except ImportError:
        return (0, 0)
    path = behavior_file_path(project.path, doc)
    if path is None or not path.exists():
        return (0, 0)
    methods = parse_handler_methods(path, behavior_class_name(doc))
    try:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        line_count = 0
    return (len(methods), line_count)


def _default_archive_target(project, doc):
    """Default ``Save copy`` destination — lives inside the project
    at ``<project>/assets/scripts_archive/<page>/<window>.py`` so
    backups stay with the project (per the user's "active scripts
    folder = working code only" principle). Returns an empty string
    for unsaved projects so the dialog still renders something
    sensible in the entry, even though the Save Copy radio will be
    irrelevant (recycle bin path also no-ops there).
    """
    if not getattr(project, "path", None):
        return ""
    try:
        from app.core.script_paths import archive_dir, slugify_window_name
    except ImportError:
        return ""
    target_dir = archive_dir(project.path)
    if target_dir is None:
        return ""
    slug = slugify_window_name(doc.name)
    return str(target_dir / f"{slug}.py")


def run_action_delete_flow(
    parent,
    project,
    widget_id: str,
    event_key: str,
    method_index: int,
    method_name: str,
) -> str | None:
    """Pop ``ActionDeleteDialog`` for an event-handler row. Returns:

    - ``"delete"`` — caller unbinds AND removes the ``def`` from the
      file via ``delete_method_from_file``.
    - ``"open_editor"`` — caller jumps to the method in the editor;
      the binding stays. (The user re-clicks ``[✕]`` once they've
      copied / saved the body.)
    - ``None`` — Cancel.

    Computes the method's line count + cross-event usage on the
    same widget so the dialog can warn when deletion would break
    other rows.
    """
    line_count = _count_method_lines(project, widget_id, method_name)
    also_bound = _count_other_bindings(
        project, widget_id, event_key, method_index, method_name,
    )
    dialog = ActionDeleteDialog(
        parent,
        method_name=method_name,
        line_count=line_count,
        also_bound_elsewhere=also_bound,
    )
    parent.wait_window(dialog)
    if dialog.action in ("delete", "open_editor"):
        return dialog.action
    return None


def _count_method_lines(project, widget_id: str, method_name: str) -> int:
    if not getattr(project, "path", None):
        return 0
    doc = project.find_document_for_widget(widget_id)
    if doc is None:
        return 0
    try:
        from app.core.script_paths import (
            behavior_class_name, behavior_file_path,
        )
        from app.io.scripts import find_handler_method
        import ast
    except ImportError:
        return 0
    path = behavior_file_path(project.path, doc)
    if path is None or not path.exists():
        return 0
    line = find_handler_method(
        path, behavior_class_name(doc), method_name,
    )
    if line is None:
        return 0
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return 0
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        if cls.name != behavior_class_name(doc):
            continue
        for stmt in cls.body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if stmt.name == method_name:
                end = stmt.end_lineno or stmt.lineno
                return max(1, end - stmt.lineno + 1)
    return 0


def _count_other_bindings(
    project, widget_id: str, current_event_key: str,
    current_index: int, method_name: str,
) -> int:
    """Count how many OTHER (event_key, index) slots on the same
    document bind ``method_name``. Used to surface a warning when
    deleting the def would orphan multiple rows at once.
    """
    doc = project.find_document_for_widget(widget_id)
    if doc is None:
        return 0
    total = 0
    stack = list(doc.root_widgets)
    while stack:
        node = stack.pop()
        for ev_key, methods in (node.handlers or {}).items():
            for idx, name in enumerate(methods):
                if name != method_name:
                    continue
                if (
                    node.id == widget_id
                    and ev_key == current_event_key
                    and idx == current_index
                ):
                    continue
                total += 1
        stack.extend(node.children)
    return total
