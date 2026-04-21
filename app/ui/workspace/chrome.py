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
CHROME_PREVIEW_TAG = "window_chrome_preview"
CHROME_PREVIEW_IMG_TAG = "window_chrome_preview_img"
CHROME_EXPORT_TAG = "window_chrome_export"
CHROME_EXPORT_IMG_TAG = "window_chrome_export_img"
CHROME_MIN_TAG = "window_chrome_min"
CHROME_CLOSE_TAG = "window_chrome_close"
CHROME_HEIGHT = 28
CHROME_BG_COLOR = "#2d2d30"
CHROME_FG_COLOR = "#cccccc"
CHROME_FG_DIM = "#666666"
CHROME_CLOSE_HOVER = "#c42b1c"

# Shared drag threshold (also used by the widget drag controller).
DRAG_THRESHOLD = 4

# Past this widget count the per-motion ``apply_all`` (per-widget
# configure + font rebuild) turns document dragging into a slide show.
# Hide widgets while the user drags and resync once on release.
HIDE_THRESHOLD = 10

# Button x-offsets from the right edge of the document rectangle —
# laid out right-to-left in the title bar: close (✕) → min (−) →
# tofront (⇧) → toback (⇩) → settings (⚙).
CLOSE_X_OFFSET = 20
MIN_X_OFFSET = 48
SETTINGS_X_OFFSET = 78
TOFRONT_X_OFFSET = 108
TOBACK_X_OFFSET = 138
# Dialog-only "▶ Preview this dialog" button — launches a hidden-root
# subprocess that opens just this Toplevel. Placed farthest from the
# right edge so it doesn't compete with the destructive close button.
PREVIEW_X_OFFSET = 168
# Dialog-only "Export this dialog" button — single-document export
# to standalone .py. Sits just left of the preview icon.
EXPORT_X_OFFSET = 198
# Half-width of the invisible hit-rect that sits behind each icon
# so clicking near the glyph (not just on its pixels) registers.
ICON_HIT_PADDING = 10


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
        # Per-dialog preview icon (▶). Dim by default, brightens on hover.
        self._preview_icon = load_tk_icon(
            "play", size=14, color=CHROME_FG_DIM,
        )
        self._preview_icon_hover = load_tk_icon(
            "play", size=14, color="#ffffff",
        )
        # Per-dialog export icon. Single-document export to standalone
        # runnable ``.py`` — mirrors the File menu's "Export Active
        # Document" for the currently-hovered Toplevel.
        self._export_icon = load_tk_icon(
            "file-code", size=14, color=CHROME_FG_DIM,
        )
        self._export_icon_hover = load_tk_icon(
            "file-code", size=14, color="#ffffff",
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

        # Chrome strip sits directly above the document rectangle —
        # mirror Renderer.redraw's canvas_scale so the title bar
        # tracks the DPI-scaled rect.
        zoom = self.zoom.canvas_scale
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
        doc_preview_tag = f"chrome_preview:{doc.id}"
        doc_preview_img_tag = f"chrome_preview_img:{doc.id}"
        doc_export_tag = f"chrome_export:{doc.id}"
        doc_export_img_tag = f"chrome_export_img:{doc.id}"
        doc_close_tag = f"chrome_close:{doc.id}"
        # Umbrella tag covering every chrome canvas item that belongs
        # to this document. Used by ``drive_drag`` to slide the whole
        # strip with a single ``canvas.move`` instead of a full
        # ``_redraw_document`` per motion tick — each motion was
        # otherwise deleting + recreating ~8 canvas items per doc.
        doc_tag = f"chrome_doc:{doc.id}"

        bg_fill = CHROME_BG_COLOR if is_active else "#222222"
        # Every document wears its own accent colour — active or not.
        # The active form is still distinguished by the chrome bg and
        # the trailing '*', so the colour just tells you which is
        # which, not which one is focused.
        title_fg = self.project.get_accent_color(doc.id)

        self.canvas.create_rectangle(
            left, top, right, doc_top,
            fill=bg_fill, outline=bg_fill,
            tags=(CHROME_TAG, CHROME_BG_TAG, doc_bg_tag, doc_tag),
        )
        self.canvas.create_text(
            left + 14, mid,
            text=title_raw,
            anchor="w",
            fill=title_fg,
            font=("Segoe UI", 10),
            tags=(CHROME_TAG, CHROME_TITLE_TAG, doc_title_tag, doc_tag),
        )
        if self._settings_icon is not None:
            self._draw_icon_button(
                right - SETTINGS_X_OFFSET, top, doc_top, mid, bg_fill,
                self._settings_icon,
                rect_tags=(
                    CHROME_TAG, CHROME_SETTINGS_TAG,
                    doc_settings_tag, doc_tag,
                ),
                image_tags=(
                    CHROME_TAG, CHROME_SETTINGS_TAG,
                    CHROME_SETTINGS_IMG_TAG,
                    doc_settings_tag, doc_settings_img_tag, doc_tag,
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
        # Send-to-Back also makes sense when a doc is at index 0 but
        # currently active — ``active=top`` render sort means it's
        # visually on top of everyone else, so the button deactivates
        # it (promoting the next topmost).
        can_to_back = len(docs) > 1 and (doc_idx > 0 or is_active)
        if self._tofront_icon is not None and can_to_front:
            self._draw_icon_button(
                right - TOFRONT_X_OFFSET, top, doc_top, mid, bg_fill,
                self._tofront_icon,
                rect_tags=(
                    CHROME_TAG, CHROME_TOFRONT_TAG,
                    doc_tofront_tag, doc_tag,
                ),
                image_tags=(
                    CHROME_TAG, CHROME_TOFRONT_TAG,
                    CHROME_TOFRONT_IMG_TAG,
                    doc_tofront_tag, doc_tofront_img_tag, doc_tag,
                ),
            )
        if self._toback_icon is not None and can_to_back:
            self._draw_icon_button(
                right - TOBACK_X_OFFSET, top, doc_top, mid, bg_fill,
                self._toback_icon,
                rect_tags=(
                    CHROME_TAG, CHROME_TOBACK_TAG,
                    doc_toback_tag, doc_tag,
                ),
                image_tags=(
                    CHROME_TAG, CHROME_TOBACK_TAG,
                    CHROME_TOBACK_IMG_TAG,
                    doc_toback_tag, doc_toback_img_tag, doc_tag,
                ),
            )
        # "▶ Preview" — only on Toplevel dialogs. The main window has
        # Ctrl+R for full-project preview; per-dialog preview is how
        # the designer tests a Toplevel without wiring a real button.
        if doc.is_toplevel and self._preview_icon is not None:
            self._draw_icon_button(
                right - PREVIEW_X_OFFSET, top, doc_top, mid, bg_fill,
                self._preview_icon,
                rect_tags=(
                    CHROME_TAG, CHROME_PREVIEW_TAG,
                    doc_preview_tag, doc_tag,
                ),
                image_tags=(
                    CHROME_TAG, CHROME_PREVIEW_TAG,
                    CHROME_PREVIEW_IMG_TAG,
                    doc_preview_tag, doc_preview_img_tag, doc_tag,
                ),
            )
        # Export — also Toplevel-only. Same standalone-export behaviour
        # as File → Export Active Document, triggered per-form.
        if doc.is_toplevel and self._export_icon is not None:
            self._draw_icon_button(
                right - EXPORT_X_OFFSET, top, doc_top, mid, bg_fill,
                self._export_icon,
                rect_tags=(
                    CHROME_TAG, CHROME_EXPORT_TAG,
                    doc_export_tag, doc_tag,
                ),
                image_tags=(
                    CHROME_TAG, CHROME_EXPORT_TAG,
                    CHROME_EXPORT_IMG_TAG,
                    doc_export_tag, doc_export_img_tag, doc_tag,
                ),
            )
        self.canvas.create_text(
            right - MIN_X_OFFSET, mid,
            text="−",
            anchor="center",
            fill=CHROME_FG_DIM,
            font=("Segoe UI", 16, "bold"),
            tags=(CHROME_TAG, CHROME_MIN_TAG, doc_tag),
        )
        self.canvas.create_text(
            right - CLOSE_X_OFFSET, mid,
            text="✕",
            anchor="center",
            fill=title_fg,
            font=("Segoe UI", 12, "bold"),
            tags=(
                CHROME_TAG, CHROME_CLOSE_TAG,
                doc_close_tag, doc_tag,
            ),
        )
        self._bind_for_document(
            doc,
            doc_bg_tag, doc_title_tag,
            doc_settings_tag, doc_settings_img_tag, doc_close_tag,
            doc_tofront_tag, doc_tofront_img_tag,
            doc_toback_tag, doc_toback_img_tag,
            doc_preview_tag, doc_preview_img_tag,
            doc_export_tag, doc_export_img_tag,
        )

    def _draw_icon_button(
        self, cx: int, top: int, doc_top: int, mid: int,
        bg_fill: str, icon,
        rect_tags: tuple, image_tags: tuple,
    ) -> None:
        """Paint a titlebar icon button as a hit rectangle + image.
        ``rect_tags`` and ``image_tags`` carry the per-doc + shared
        tags the caller needs — this helper just removes the
        create_rectangle + create_image boilerplate that used to
        repeat for every button (settings / tofront / toback).
        """
        self.canvas.create_rectangle(
            cx - ICON_HIT_PADDING, top + 2,
            cx + ICON_HIT_PADDING, doc_top - 2,
            fill=bg_fill, outline="",
            tags=rect_tags,
        )
        self.canvas.create_image(
            cx, mid,
            image=icon, anchor="center",
            tags=image_tags,
        )

    def _bind_icon_hover(
        self, trigger_tag: str, img_tag: str,
        icon_normal, icon_hover, on_click,
    ) -> None:
        """Wire <Button-1> + <Enter>/<Leave> on a titlebar icon tag.
        Settings / tofront / toback all share the same pattern —
        click runs ``on_click``, hover swaps the image to
        ``icon_hover`` + hand cursor, leave restores both.
        """
        self.canvas.tag_bind(
            trigger_tag, "<Button-1>",
            lambda _e: on_click(),
        )
        self.canvas.tag_bind(
            trigger_tag, "<Enter>",
            lambda _e, t=img_tag: self._set_icon_hover(
                t, icon_hover, cursor="hand2",
            ),
        )
        self.canvas.tag_bind(
            trigger_tag, "<Leave>",
            lambda _e, t=img_tag: self._set_icon_hover(
                t, icon_normal, cursor="",
            ),
        )

    def _bind_for_document(
        self, doc, bg_tag, title_tag,
        settings_tag, settings_img_tag, close_tag,
        tofront_tag, tofront_img_tag, toback_tag, toback_img_tag,
        preview_tag=None, preview_img_tag=None,
        export_tag=None, export_img_tag=None,
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
        # Icon click callbacks return "break" so propagation to the
        # chrome bg / title bindings (drag start) is stopped — without
        # it a click on the settings icon would kick off a doc drag
        # gesture under the button.
        self._bind_icon_hover(
            settings_tag, settings_img_tag,
            self._settings_icon, self._settings_icon_hover,
            on_click=lambda d=doc_id: self._on_settings_click(None, d),
        )
        self._bind_icon_hover(
            tofront_tag, tofront_img_tag,
            self._tofront_icon, self._tofront_icon_hover,
            on_click=lambda d=doc_id: self._on_tofront_click(d),
        )
        self._bind_icon_hover(
            toback_tag, toback_img_tag,
            self._toback_icon, self._toback_icon_hover,
            on_click=lambda d=doc_id: self._on_toback_click(d),
        )
        if (
            preview_tag and preview_img_tag
            and doc.is_toplevel and self._preview_icon is not None
        ):
            self._bind_icon_hover(
                preview_tag, preview_img_tag,
                self._preview_icon, self._preview_icon_hover,
                on_click=lambda d=doc_id: self._on_preview_click(d),
            )
        if (
            export_tag and export_img_tag
            and doc.is_toplevel and self._export_icon is not None
        ):
            self._bind_icon_hover(
                export_tag, export_img_tag,
                self._export_icon, self._export_icon_hover,
                on_click=lambda d=doc_id: self._on_export_click(d),
            )
        # Close button — text item, hover flips fill color instead of
        # an image swap, so it doesn't fit ``_bind_icon_hover``.
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

    def _set_icon_hover(
        self, tag: str, icon, cursor: str = "hand2",
    ) -> None:
        """Swap an icon canvas image + set the canvas cursor. Pass
        ``cursor=""`` on <Leave> to restore the default cursor;
        earlier the cursor stayed ``hand2`` after leaving tofront /
        toback because both enter and leave called this with the
        same implicit cursor argument.
        """
        if icon is None:
            return
        try:
            self.canvas.itemconfigure(tag, image=icon)
            self.canvas.configure(cursor=cursor)
        except tk.TclError:
            pass

    def _on_tofront_click(self, doc_id: str) -> str:
        self.project.bring_document_to_front(doc_id)
        return "break"

    def _on_toback_click(self, doc_id: str) -> str:
        self.project.send_document_to_back(doc_id)
        return "break"

    def _on_preview_click(self, doc_id: str) -> str:
        """Launch a dialog-only preview subprocess — hidden root host
        + this Toplevel on top. Routes through the workspace's event
        bus so main_window owns the subprocess lifecycle (same place
        Ctrl+R is handled).
        """
        self.project.event_bus.publish(
            "request_preview_dialog", doc_id,
        )
        return "break"

    def _on_export_click(self, doc_id: str) -> str:
        """Export just this dialog as a standalone .py — routes
        through the event bus so main_window owns the file dialog
        + write flow (same handler as File → Export Active Document).
        """
        self.project.event_bus.publish(
            "request_export_document", doc_id,
        )
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

        Motion avoids ``_redraw_document`` — that would delete +
        recreate every document's chrome / outline / grid on every
        tick. Instead we compute the per-tick pixel delta and shift
        the dragged doc's items via three ``canvas.move`` calls on
        per-doc tags. Widgets still ride through ``apply_all`` (or
        stay hidden in ghost mode). ``end_drag`` runs one final full
        redraw so the release state is clean.
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
            # First real motion — decide whether to hide the doc's
            # widgets. apply_all per motion for a 20+ widget form is
            # the main slowdown; hiding cuts the whole loop.
            doc = self.project.get_document(drag["doc_id"])
            if (
                doc is not None
                and self._count_doc_widgets(doc) >= HIDE_THRESHOLD
            ):
                self._enter_hidden_mode(doc)
        # Converting root-pixel delta → logical units uses
        # canvas_scale because the cursor moves in physical pixels on
        # a DPI-aware process — same multiplier the doc rect under it
        # uses in Renderer.redraw.
        zoom = self.zoom.canvas_scale or 1.0
        dx_logical = int((event.x_root - drag["press_x_root"]) / zoom)
        dy_logical = int((event.y_root - drag["press_y_root"]) / zoom)
        doc = self.project.get_document(drag["doc_id"])
        if doc is None:
            return "break"
        # Per-tick pixel delta derived from the logical model update.
        # Going through the model (and clamping to 0) keeps canvas.move
        # honest even when the cursor tries to push the doc off-canvas
        # into the negative region — we stop translating exactly when
        # the model clamps.
        prev_canvas_x = doc.canvas_x
        prev_canvas_y = doc.canvas_y
        new_canvas_x = max(0, drag["start_canvas_x"] + dx_logical)
        new_canvas_y = max(0, drag["start_canvas_y"] + dy_logical)
        dx_pixel = int((new_canvas_x - prev_canvas_x) * zoom)
        dy_pixel = int((new_canvas_y - prev_canvas_y) * zoom)
        doc.canvas_x = new_canvas_x
        doc.canvas_y = new_canvas_y
        if dx_pixel or dy_pixel:
            doc_id = drag["doc_id"]
            for tag in (
                f"chrome_doc:{doc_id}",
                f"doc_rect:{doc_id}",
                f"grid:{doc_id}",
            ):
                try:
                    self.canvas.move(tag, dx_pixel, dy_pixel)
                except tk.TclError:
                    pass
        if not drag.get("hidden_mode"):
            self.zoom.apply_all()
            if self.project.selected_id:
                # Full ``draw`` — not ``update`` — so multi-select
                # outlines for non-primary widgets refresh too. A
                # ``update`` would move only the primary chrome and
                # leave the non-primary outlines parked at their
                # pre-drag positions.
                self.workspace.selection.draw()
        return "break"

    def _count_doc_widgets(self, doc) -> int:
        count = 0
        stack = list(doc.root_widgets)
        while stack:
            node = stack.pop()
            count += 1
            stack.extend(node.children)
        return count

    def _enter_hidden_mode(self, doc) -> None:
        """Hide every top-level canvas item in ``doc`` plus any
        selection chrome bound to widgets in ``doc``. Stores the hidden
        ids on ``self._drag`` so release can unhide exactly what it
        hid — nested place children follow their parent Frame's hidden
        state automatically, so we only need top-level tagging.
        """
        if self._drag is None:
            return
        hidden_window_ids: list = []
        for node in doc.root_widgets:
            entry = self.workspace.widget_views.get(node.id)
            if entry is None:
                continue
            _, window_id = entry
            if window_id is None:
                continue
            try:
                self.canvas.itemconfigure(window_id, state="hidden")
            except tk.TclError:
                continue
            hidden_window_ids.append(window_id)
        hidden_chrome_tags: list = []
        selected_ids = getattr(self.project, "selected_ids", set()) or set()
        for wid in selected_ids:
            wid_doc = self.project.find_document_for_widget(wid)
            if wid_doc is not doc:
                continue
            tag = f"chrome_wid_{wid}"
            try:
                self.canvas.itemconfigure(tag, state="hidden")
            except tk.TclError:
                continue
            hidden_chrome_tags.append(tag)
        self._drag["hidden_mode"] = True
        self._drag["hidden_window_ids"] = hidden_window_ids
        self._drag["hidden_chrome_tags"] = hidden_chrome_tags
        # Signals ``Renderer.update_visibility_across_docs`` to skip
        # the per-motion state flip so our hidden widgets stay hidden.
        self.workspace._doc_drag_hide_active = True

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
        # Hide-mode teardown — unhide before any further redraws so
        # the user doesn't see a frame of ghosted widgets mid-release.
        if drag.get("hidden_mode"):
            # Clear the flag first so the release-time visibility
            # refresh (inside apply_all → _on_zoom_changed → render)
            # actually runs and picks up the widgets' new positions.
            self.workspace._doc_drag_hide_active = False
            for window_id in drag.get("hidden_window_ids", []):
                try:
                    self.canvas.itemconfigure(window_id, state="normal")
                except tk.TclError:
                    pass
            for tag in drag.get("hidden_chrome_tags", []):
                try:
                    self.canvas.itemconfigure(tag, state="normal")
                except tk.TclError:
                    pass
            # apply_all was skipped during motion — run it once now so
            # widgets jump to the doc's final offset before the chrome
            # is redrawn and the selection handles are resynced.
            self.zoom.apply_all()
            if self.project.selected_id:
                # ``draw`` (not ``update``) so multi-select outlines
                # follow the doc to its new position; ``update`` only
                # repositions the primary chrome.
                self.workspace.selection.draw()
        if not drag["moved"]:
            # Click without drag → activate the document (settings
            # icon handles the "open Properties" case separately).
            self.project.set_active_document(doc_id)
            self.workspace._redraw_document()
            return "break"
        doc = self.project.get_document(doc_id)
        if doc is None:
            return "break"
        # Full redraw on release — ``drive_drag`` skipped
        # ``_redraw_document`` to avoid per-motion churn, so now we
        # rebuild the doc rect / chrome / grid from scratch at the
        # final position + run the cross-doc visibility mask.
        self.workspace._redraw_document()
        before = (drag["start_canvas_x"], drag["start_canvas_y"])
        after = (doc.canvas_x, doc.canvas_y)
        if before != after:
            self.project.history.push(
                MoveDocumentCommand(doc_id, before, after),
            )
        return "break"
