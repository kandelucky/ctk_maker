"""Document drag-to-move sidecar for ``ChromeManager``.

Owns the title-bar drag gesture: press captures the doc's starting
canvas position + activates it, motion translates the press delta
into per-doc canvas moves (skipping the full ``_redraw_document``
for perf), and release pushes one ``MoveDocumentCommand`` if the
doc actually moved.

Two threshold-driven mode switches:

* **Hidden mode** (kicks in when the dragged doc has ≥ ``HIDE_THRESHOLD``
  widgets) — hides every top-level canvas item in the doc plus any
  selection chrome bound to its widgets so motion stays smooth. The
  ``_doc_drag_hide_active`` flag on the workspace tells
  ``Renderer.update_visibility_across_docs`` to skip the per-motion
  state flip while this is on.
* **Canvas-level motion fallback** (``drive_drag``) — ``tag_bind``
  motion stops firing the instant the cursor slips off the title bar
  item, but the canvas-level ``<B1-Motion>`` keeps catching events
  while Button-1 is held; ``Workspace._on_canvas_motion`` (in
  marquee.py) routes those back here so the drag survives.
"""
from __future__ import annotations

import tkinter as tk


# Shared drag threshold (also used by the widget drag controller).
DRAG_THRESHOLD = 4

# Past this widget count the per-motion ``apply_all`` (per-widget
# configure + font rebuild) turns document dragging into a slide show.
# Hide widgets while the user drags and resync once on release.
HIDE_THRESHOLD = 10


class ChromeDrag:
    """Per-chrome document drag handler. See module docstring."""

    def __init__(self, chrome) -> None:
        self.chrome = chrome

    def on_press(self, event, doc_id: str) -> str:
        # Capture the starting logical position of this document so
        # motion events can slide it around the canvas.
        chrome = self.chrome
        doc = chrome.project.get_document(doc_id)
        if doc is None:
            return "break"
        chrome._drag = {
            "doc_id": doc_id,
            "start_canvas_x": doc.canvas_x,
            "start_canvas_y": doc.canvas_y,
            "press_x_root": event.x_root,
            "press_y_root": event.y_root,
            "moved": False,
        }
        # Activate the clicked document up front so the title bar
        # immediately reflects focus during the drag.
        chrome.project.set_active_document(doc_id)
        return "break"

    def on_motion(self, event, _doc_id: str) -> str:
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
        chrome = self.chrome
        drag = chrome._drag
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
            doc = chrome.project.get_document(drag["doc_id"])
            if (
                doc is not None
                and self._count_doc_widgets(doc) >= HIDE_THRESHOLD
            ):
                self._enter_hidden_mode(doc)
        # Converting root-pixel delta → logical units uses
        # canvas_scale because the cursor moves in physical pixels on
        # a DPI-aware process — same multiplier the doc rect under it
        # uses in Renderer.redraw.
        zoom = chrome.zoom.canvas_scale or 1.0
        dx_logical = int((event.x_root - drag["press_x_root"]) / zoom)
        dy_logical = int((event.y_root - drag["press_y_root"]) / zoom)
        doc = chrome.project.get_document(drag["doc_id"])
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
                    chrome.canvas.move(tag, dx_pixel, dy_pixel)
                except tk.TclError:
                    pass
        if not drag.get("hidden_mode"):
            chrome.zoom.apply_all()
            if chrome.project.selected_id:
                # Full ``draw`` — not ``update`` — so multi-select
                # outlines for non-primary widgets refresh too. A
                # ``update`` would move only the primary chrome and
                # leave the non-primary outlines parked at their
                # pre-drag positions.
                chrome.workspace.selection.draw()
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
        ids on ``chrome._drag`` so release can unhide exactly what it
        hid — nested place children follow their parent Frame's hidden
        state automatically, so we only need top-level tagging.
        """
        chrome = self.chrome
        if chrome._drag is None:
            return
        hidden_window_ids: list = []
        for node in doc.root_widgets:
            entry = chrome.workspace.widget_views.get(node.id)
            if entry is None:
                continue
            _, window_id = entry
            if window_id is None:
                continue
            try:
                chrome.canvas.itemconfigure(window_id, state="hidden")
            except tk.TclError:
                continue
            hidden_window_ids.append(window_id)
        hidden_chrome_tags: list = []
        selected_ids = (
            getattr(chrome.project, "selected_ids", set()) or set()
        )
        for wid in selected_ids:
            wid_doc = chrome.project.find_document_for_widget(wid)
            if wid_doc is not doc:
                continue
            tag = f"chrome_wid_{wid}"
            try:
                chrome.canvas.itemconfigure(tag, state="hidden")
            except tk.TclError:
                continue
            hidden_chrome_tags.append(tag)
        chrome._drag["hidden_mode"] = True
        chrome._drag["hidden_window_ids"] = hidden_window_ids
        chrome._drag["hidden_chrome_tags"] = hidden_chrome_tags
        # Signals ``Renderer.update_visibility_across_docs`` to skip
        # the per-motion state flip so our hidden widgets stay hidden.
        chrome.workspace._doc_drag_hide_active = True

    def on_release(
        self, _event=None, doc_id: str | None = None,
    ) -> str:
        return self.end_drag(doc_id)

    def end_drag(self, doc_id: str | None) -> str:
        """Finish a chrome drag gesture — idempotent, safe to call
        from a canvas-level release handler too.
        """
        from app.core.commands import MoveDocumentCommand
        chrome = self.chrome
        drag = chrome._drag
        chrome._drag = None
        if drag is None or doc_id is None:
            return "break"
        # Hide-mode teardown — unhide before any further redraws so
        # the user doesn't see a frame of ghosted widgets mid-release.
        if drag.get("hidden_mode"):
            # Clear the flag first so the release-time visibility
            # refresh (inside apply_all → _on_zoom_changed → render)
            # actually runs and picks up the widgets' new positions.
            chrome.workspace._doc_drag_hide_active = False
            for window_id in drag.get("hidden_window_ids", []):
                try:
                    chrome.canvas.itemconfigure(window_id, state="normal")
                except tk.TclError:
                    pass
            for tag in drag.get("hidden_chrome_tags", []):
                try:
                    chrome.canvas.itemconfigure(tag, state="normal")
                except tk.TclError:
                    pass
            # apply_all was skipped during motion — run it once now so
            # widgets jump to the doc's final offset before the chrome
            # is redrawn and the selection handles are resynced.
            chrome.zoom.apply_all()
            if chrome.project.selected_id:
                # ``draw`` (not ``update``) so multi-select outlines
                # follow the doc to its new position; ``update`` only
                # repositions the primary chrome.
                chrome.workspace.selection.draw()
        if not drag["moved"]:
            # Click without drag → activate the document (settings
            # icon handles the "open Properties" case separately).
            chrome.project.set_active_document(doc_id)
            chrome.workspace._redraw_document()
            return "break"
        doc = chrome.project.get_document(doc_id)
        if doc is None:
            return "break"
        # Full redraw on release — ``drive_drag`` skipped
        # ``_redraw_document`` to avoid per-motion churn, so now we
        # rebuild the doc rect / chrome / grid from scratch at the
        # final position + run the cross-doc visibility mask.
        chrome.workspace._redraw_document()
        before = (drag["start_canvas_x"], drag["start_canvas_y"])
        after = (doc.canvas_x, doc.canvas_y)
        if before != after:
            chrome.project.history.push(
                MoveDocumentCommand(doc_id, before, after),
            )
        return "break"
