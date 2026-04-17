"""Per-document chrome strip — title bar, ⚙ / ✕ buttons, drag-to-move.

Every document on the canvas gets a title bar rendered above its
rectangle. The strip shows the document name, the current layout-type
suffix (``· vertical`` / ``· horizontal`` / ``· grid``), a settings
icon (opens the Window properties) and a close glyph. Clicking /
dragging the strip activates + moves THAT document only — never the
others, even when they overlap.

Split out of the old monolithic ``workspace.py`` to keep chrome
drawing + events in a single focused module. Core ``Workspace``
holds a single instance on ``self.chrome`` and delegates to it.

External callers of the old private helpers (``_draw_single_chrome``,
``_remove_document``, …) should go through the public methods here —
the Workspace stubs that remain are thin backwards-compat shims.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app.ui.icons import load_tk_icon
from app.widgets.layout_schema import (
    LAYOUT_DISPLAY_NAMES,
    normalise_layout_type,
)

# Canvas tags — shared between chrome and the outer canvas motion
# handlers that peek at ``CHROME_TAG`` to decide whether the click
# belongs to chrome.
CHROME_TAG = "window_chrome"
CHROME_BG_TAG = "window_chrome_bg"
CHROME_TITLE_TAG = "window_chrome_title"
CHROME_SETTINGS_TAG = "window_chrome_settings"
CHROME_SETTINGS_IMG_TAG = "window_chrome_settings_img"
CHROME_TOFRONT_TAG = "window_chrome_tofront"
CHROME_TOFRONT_IMG_TAG = "window_chrome_tofront_img"
CHROME_TOBACK_TAG = "window_chrome_toback"
CHROME_TOBACK_IMG_TAG = "window_chrome_toback_img"
CHROME_MIN_TAG = "window_chrome_min"
CHROME_CLOSE_TAG = "window_chrome_close"
CHROME_HEIGHT = 28
CHROME_BG_COLOR = "#2d2d30"
CHROME_FG_COLOR = "#cccccc"
CHROME_FG_DIM = "#666666"
CHROME_CLOSE_HOVER = "#c42b1c"

# Shared drag threshold (also used by the widget drag controller).
DRAG_THRESHOLD = 4


class ChromeManager:
    """Per-workspace chrome (title bar) renderer + drag handler.

    Owns the two settings icons and the drag-in-progress state. All
    other state (document list, active id, dirty flag, selection,
    zoom) is read through the workspace ref so both modules stay in
    sync with a single source of truth.
    """

    def __init__(self, workspace) -> None:
        self.workspace = workspace
        # tk PhotoImage pair for the title-bar settings icon. Dim +
        # bright variants swapped via itemconfigure on hover. Kept
        # here so tk doesn't garbage-collect them.
        self._settings_icon = load_tk_icon(
            "settings", size=14, color=CHROME_FG_DIM,
        )
        self._settings_icon_hover = load_tk_icon(
            "settings", size=14, color="#ffffff",
        )
        # Z-order icons (Bring to Front / Send to Back). Double
        # chevrons read as "all the way" vs a single step.
        self._tofront_icon = load_tk_icon(
            "chevrons-up", size=14, color=CHROME_FG_DIM,
        )
        self._tofront_icon_hover = load_tk_icon(
            "chevrons-up", size=14, color="#ffffff",
        )
        self._toback_icon = load_tk_icon(
            "chevrons-down", size=14, color=CHROME_FG_DIM,
        )
        self._toback_icon_hover = load_tk_icon(
            "chevrons-down", size=14, color="#ffffff",
        )
        self._drag: dict | None = None

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    @property
    def canvas(self) -> tk.Canvas:
        return self.workspace.canvas

    @property
    def zoom(self):
        return self.workspace.zoom

    @property
    def project(self):
        return self.workspace.project

    def is_dragging(self) -> bool:
        return self._drag is not None

    def current_drag_doc_id(self) -> str | None:
        return self._drag.get("doc_id") if self._drag is not None else None

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw_for(self, doc) -> None:
        """Render the title strip for one document + wire its events.
        Called per-doc from ``Renderer.redraw`` so stacking order
        matches widget rendering.
        """
        from app.ui.workspace.render import DOCUMENT_PADDING

        zoom = self.zoom.value
        dw = int(doc.width * zoom)
        pad = DOCUMENT_PADDING
        doc_left = pad + int(doc.canvas_x * zoom)
        doc_top = pad + int(doc.canvas_y * zoom)
        top = doc_top - CHROME_HEIGHT
        mid = top + CHROME_HEIGHT // 2
        left = doc_left
        right = doc_left + dw

        title_raw = str(doc.name or "Untitled")
        is_active = doc.id == self.project.active_document_id
        if is_active and self.workspace._dirty:
            title_raw = f"{title_raw} *"
        layout = normalise_layout_type(
            doc.window_properties.get("layout_type", "place"),
        )
        if layout != "place":
            display = LAYOUT_DISPLAY_NAMES.get(layout, layout).lower()
            title_raw = f"{title_raw}  · {display}"
        max_chars = max(8, dw // 9)
        if len(title_raw) > max_chars:
            title_raw = title_raw[: max_chars - 1] + "…"

        # Per-document tags so hit-testing + drag know *which*
        # document the click landed on.
        doc_bg_tag = f"chrome_bg:{doc.id}"
        doc_title_tag = f"chrome_title:{doc.id}"
        doc_settings_tag = f"chrome_settings:{doc.id}"
        doc_settings_img_tag = f"chrome_settings_img:{doc.id}"
        doc_tofront_tag = f"chrome_tofront:{doc.id}"
        doc_tofront_img_tag = f"chrome_tofront_img:{doc.id}"
        doc_toback_tag = f"chrome_toback:{doc.id}"
        doc_toback_img_tag = f"chrome_toback_img:{doc.id}"
        doc_close_tag = f"chrome_close:{doc.id}"

        bg_fill = CHROME_BG_COLOR if is_active else "#222222"
        # Every document wears its own accent colour — active or not.
        # The active form is still distinguished by the chrome bg and
        # the trailing '*', so the colour just tells you which is
        # which, not which one is focused.
        title_fg = self.project.get_accent_color(doc.id)

        self.canvas.create_rectangle(
            left, top, right, doc_top,
            fill=bg_fill, outline=bg_fill,
            tags=(CHROME_TAG, CHROME_BG_TAG, doc_bg_tag),
        )
        self.canvas.create_text(
            left + 14, mid,
            text=title_raw,
            anchor="w",
            fill=title_fg,
            font=("Segoe UI", 10),
            tags=(CHROME_TAG, CHROME_TITLE_TAG, doc_title_tag),
        )
        if self._settings_icon is not None:
            sx = right - 78
            self.canvas.create_rectangle(
                sx - 10, top + 2, sx + 10, doc_top - 2,
                fill=bg_fill, outline="",
                tags=(CHROME_TAG, CHROME_SETTINGS_TAG, doc_settings_tag),
            )
            self.canvas.create_image(
                sx, mid,
                image=self._settings_icon,
                anchor="center",
                tags=(
                    CHROME_TAG, CHROME_SETTINGS_TAG,
                    CHROME_SETTINGS_IMG_TAG,
                    doc_settings_tag, doc_settings_img_tag,
                ),
            )

        # Z-order buttons — conditional visibility.
        # Bring to Front (↑): hidden when this doc is already active
        # (the active=top sort already puts it on top). Send to Back
        # (↓): hidden when the doc is the first in the list (already
        # at the back).
        docs = self.project.documents
        doc_idx = docs.index(doc) if doc in docs else 0
        can_to_front = not is_active
        can_to_back = doc_idx > 0
        if self._tofront_icon is not None and can_to_front:
            fx = right - 108
            self.canvas.create_rectangle(
                fx - 10, top + 2, fx + 10, doc_top - 2,
                fill=bg_fill, outline="",
                tags=(CHROME_TAG, CHROME_TOFRONT_TAG, doc_tofront_tag),
            )
            self.canvas.create_image(
                fx, mid,
                image=self._tofront_icon,
                anchor="center",
                tags=(
                    CHROME_TAG, CHROME_TOFRONT_TAG,
                    CHROME_TOFRONT_IMG_TAG,
                    doc_tofront_tag, doc_tofront_img_tag,
                ),
            )
        if self._toback_icon is not None and can_to_back:
            bx = right - 138
            self.canvas.create_rectangle(
                bx - 10, top + 2, bx + 10, doc_top - 2,
                fill=bg_fill, outline="",
                tags=(CHROME_TAG, CHROME_TOBACK_TAG, doc_toback_tag),
            )
            self.canvas.create_image(
                bx, mid,
                image=self._toback_icon,
                anchor="center",
                tags=(
                    CHROME_TAG, CHROME_TOBACK_TAG,
                    CHROME_TOBACK_IMG_TAG,
                    doc_toback_tag, doc_toback_img_tag,
                ),
            )
        self.canvas.create_text(
            right - 48, mid,
            text="−",
            anchor="center",
            fill=CHROME_FG_DIM,
            font=("Segoe UI", 16, "bold"),
            tags=(CHROME_TAG, CHROME_MIN_TAG),
        )
        self.canvas.create_text(
            right - 20, mid,
            text="✕",
            anchor="center",
            fill=title_fg,
            font=("Segoe UI", 12, "bold"),
            tags=(CHROME_TAG, CHROME_CLOSE_TAG, doc_close_tag),
        )
        self._bind_for_document(
            doc,
            doc_bg_tag, doc_title_tag,
            doc_settings_tag, doc_close_tag,
            doc_tofront_tag, doc_tofront_img_tag,
            doc_toback_tag, doc_toback_img_tag,
        )

    def _bind_for_document(
        self, doc, bg_tag, title_tag, settings_tag, close_tag,
        tofront_tag, tofront_img_tag, toback_tag, toback_img_tag,
    ) -> None:
        """Wire the click / drag / hover bindings for a single
        document's chrome strip. Each document gets its own tag
        namespace (``chrome_bg:{doc.id}`` etc.) so handlers know
        which form to mutate — essential for multi-document layouts
        where dragging one form must not touch the others.
        """
        doc_id = doc.id
        for tag in (bg_tag, title_tag):
            self.canvas.tag_bind(
                tag, "<ButtonPress-1>",
                lambda e, d=doc_id: self._on_press(e, d),
            )
            self.canvas.tag_bind(
                tag, "<B1-Motion>",
                lambda e, d=doc_id: self._on_motion(e, d),
            )
            self.canvas.tag_bind(
                tag, "<ButtonRelease-1>",
                lambda e, d=doc_id: self._on_release(e, d),
            )
            self.canvas.tag_bind(
                tag, "<Enter>",
                lambda _e: self._set_cursor("fleur"),
            )
            self.canvas.tag_bind(
                tag, "<Leave>",
                lambda _e: self._set_cursor(""),
            )
        self.canvas.tag_bind(
            settings_tag, "<Button-1>",
            lambda e, d=doc_id: self._on_settings_click(e, d),
        )
        self.canvas.tag_bind(
            settings_tag, "<Enter>", self._on_settings_enter,
        )
        self.canvas.tag_bind(
            settings_tag, "<Leave>", self._on_settings_leave,
        )
        self.canvas.tag_bind(
            close_tag, "<Button-1>",
            lambda e, d=doc_id: self._on_close_click(e, d),
        )
        self.canvas.tag_bind(
            close_tag, "<Enter>",
            lambda _e, t=close_tag: self.canvas.itemconfigure(
                t, fill=CHROME_CLOSE_HOVER,
            ),
        )
        self.canvas.tag_bind(
            close_tag, "<Leave>",
            lambda _e, t=close_tag: self.canvas.itemconfigure(
                t, fill=CHROME_FG_COLOR,
            ),
        )

        # Bring to Front
        self.canvas.tag_bind(
            tofront_tag, "<Button-1>",
            lambda _e, d=doc_id: self._on_tofront_click(d),
        )
        self.canvas.tag_bind(
            tofront_tag, "<Enter>",
            lambda _e, t=tofront_img_tag: self._set_icon_hover(
                t, self._tofront_icon_hover,
            ),
        )
        self.canvas.tag_bind(
            tofront_tag, "<Leave>",
            lambda _e, t=tofront_img_tag: self._set_icon_hover(
                t, self._tofront_icon,
            ),
        )

        # Send to Back
        self.canvas.tag_bind(
            toback_tag, "<Button-1>",
            lambda _e, d=doc_id: self._on_toback_click(d),
        )
        self.canvas.tag_bind(
            toback_tag, "<Enter>",
            lambda _e, t=toback_img_tag: self._set_icon_hover(
                t, self._toback_icon_hover,
            ),
        )
        self.canvas.tag_bind(
            toback_tag, "<Leave>",
            lambda _e, t=toback_img_tag: self._set_icon_hover(
                t, self._toback_icon,
            ),
        )

    def _set_icon_hover(self, tag: str, icon) -> None:
        if icon is None:
            return
        try:
            self.canvas.itemconfigure(tag, image=icon)
            self.canvas.configure(cursor="hand2")
        except tk.TclError:
            pass

    def _on_tofront_click(self, doc_id: str) -> str:
        self.project.bring_document_to_front(doc_id)
        return "break"

    def _on_toback_click(self, doc_id: str) -> str:
        self.project.send_document_to_back(doc_id)
        return "break"

    # ------------------------------------------------------------------
    # Selection + settings
    # ------------------------------------------------------------------
    def _select(self, doc_id: str | None = None) -> None:
        from app.core.project import WINDOW_ID
        if doc_id is not None:
            self.project.set_active_document(doc_id)
        self.project.select_widget(WINDOW_ID)

    def _on_settings_click(
        self, _event=None, doc_id: str | None = None,
    ) -> str:
        self._select(doc_id)
        return "break"

    def _on_settings_enter(self, _event=None) -> None:
        if self._settings_icon_hover is None:
            return
        try:
            self.canvas.itemconfigure(
                CHROME_SETTINGS_IMG_TAG,
                image=self._settings_icon_hover,
            )
            self.canvas.configure(cursor="hand2")
        except tk.TclError:
            pass

    def _on_settings_leave(self, _event=None) -> None:
        if self._settings_icon is None:
            return
        try:
            self.canvas.itemconfigure(
                CHROME_SETTINGS_IMG_TAG,
                image=self._settings_icon,
            )
            self.canvas.configure(cursor="")
        except tk.TclError:
            pass

    def _set_cursor(self, cursor: str) -> None:
        # Don't fight the current tool's cursor (Hand mode owns
        # the cursor for the whole canvas).
        if not cursor:
            cursor = self.workspace.default_tool_cursor()
        try:
            self.canvas.configure(cursor=cursor)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Close → remove document
    # ------------------------------------------------------------------
    def _on_close_click(
        self, _event=None, doc_id: str | None = None,
    ) -> str:
        # Dialog chrome close = remove that dialog from the project.
        # Main window chrome close = project-level close (File/Close).
        # Mirrors OS native behaviour.
        if doc_id is not None:
            doc = self.project.get_document(doc_id)
            if doc is not None and doc.is_toplevel:
                self.remove_document(doc_id)
                return "break"
        self.project.event_bus.publish("request_close_project")
        return "break"

    def remove_document(self, doc_id: str) -> None:
        from app.core.commands import DeleteDocumentCommand
        doc = self.project.get_document(doc_id)
        if doc is None or not doc.is_toplevel:
            return
        # Confirm before destroying the dialog — chrome ✕ used to
        # disappear silently, which was surprising when it happened
        # on an accidental click.
        confirmed = messagebox.askyesno(
            title="Remove dialog",
            message=f"Remove '{doc.name}' from the project?",
            icon="warning",
            parent=self.workspace.winfo_toplevel(),
        )
        if not confirmed:
            return
        snapshot = doc.to_dict()
        index = self.project.documents.index(doc)
        for node in list(doc.root_widgets):
            self.project.remove_widget(node.id)
        self.project.documents.remove(doc)
        if self.project.active_document_id == doc_id:
            self.project.active_document_id = (
                self.project.documents[0].id
            )
            self.project.event_bus.publish(
                "active_document_changed",
                self.project.active_document_id,
            )
        self.workspace._redraw_document()
        self.project.history.push(
            DeleteDocumentCommand(snapshot, index),
        )

    # ------------------------------------------------------------------
    # Drag
    # ------------------------------------------------------------------
    def _on_press(self, event, doc_id: str) -> str:
        # Capture the starting logical position of this document so
        # motion events can slide it around the canvas.
        doc = self.project.get_document(doc_id)
        if doc is None:
            return "break"
        self._drag = {
            "doc_id": doc_id,
            "start_canvas_x": doc.canvas_x,
            "start_canvas_y": doc.canvas_y,
            "press_x_root": event.x_root,
            "press_y_root": event.y_root,
            "moved": False,
        }
        # Activate the clicked document up front so the title bar
        # immediately reflects focus during the drag.
        self.project.set_active_document(doc_id)
        return "break"

    def _on_motion(self, event, _doc_id: str) -> str:
        # Delegated to the canvas-level motion handler once the
        # press has started — tag_bind motion stops firing the
        # instant the cursor slips off the moving chrome, but the
        # canvas-level bind catches every motion while Button-1 is
        # held. This shim just funnels the event into the same path.
        return self.drive_drag(event)

    def drive_drag(self, event) -> str:
        """Canvas-level motion fallback. Called from
        ``Workspace._on_canvas_motion`` so drags that slip off the
        title bar item keep tracking the cursor.
        """
        drag = self._drag
        if drag is None:
            return ""
        if not drag["moved"]:
            dx = abs(event.x_root - drag["press_x_root"])
            dy = abs(event.y_root - drag["press_y_root"])
            if dx < DRAG_THRESHOLD and dy < DRAG_THRESHOLD:
                return "break"
            drag["moved"] = True
        zoom = self.zoom.value or 1.0
        dx_logical = int((event.x_root - drag["press_x_root"]) / zoom)
        dy_logical = int((event.y_root - drag["press_y_root"]) / zoom)
        doc = self.project.get_document(drag["doc_id"])
        if doc is None:
            return "break"
        doc.canvas_x = max(0, drag["start_canvas_x"] + dx_logical)
        doc.canvas_y = max(0, drag["start_canvas_y"] + dy_logical)
        self.workspace._redraw_document()
        self.zoom.apply_all()
        if self.project.selected_id:
            self.workspace.selection.update()
        return "break"

    def _on_release(
        self, _event=None, doc_id: str | None = None,
    ) -> str:
        return self.end_drag(doc_id)

    def end_drag(self, doc_id: str | None) -> str:
        """Finish a chrome drag gesture — idempotent, safe to call
        from a canvas-level release handler too.
        """
        from app.core.commands import MoveDocumentCommand
        drag = self._drag
        self._drag = None
        if drag is None or doc_id is None:
            return "break"
        if not drag["moved"]:
            # Click without drag → activate the document (settings
            # icon handles the "open Properties" case separately).
            self.project.set_active_document(doc_id)
            self.workspace._redraw_document()
            return "break"
        doc = self.project.get_document(doc_id)
        if doc is None:
            return "break"
        before = (drag["start_canvas_x"], drag["start_canvas_y"])
        after = (doc.canvas_x, doc.canvas_y)
        if before != after:
            self.project.history.push(
                MoveDocumentCommand(doc_id, before, after),
            )
        return "break"
