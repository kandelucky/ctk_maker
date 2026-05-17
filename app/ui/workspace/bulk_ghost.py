"""Ghost every live doc in one shot — driven by the ghost-hint banner.

Each live (non-ghost, non-collapsed, non-empty) document is processed
sequentially: focus the doc into the viewport, settle Tk layout, then
run the existing ``project.set_document_ghost`` pipeline (which
captures real pixels via ``ImageGrab`` and swaps the widgets for a
desaturated screenshot).

One doc is spared per batch — the one the user is currently looking
at (active when any portion is in the viewport, else the doc with the
largest visible area). It stays live and is re-centered in the editor
once the batch completes, so the user doesn't end up staring at a
ghost screenshot of what they were just editing.

Progress is reported in the ghost-hint label itself (the same widget
the user clicked to start the batch) — no modal overlay, no
input-blocking grab. An overlay would land in every screenshot
because ``ImageGrab`` reads on-screen pixels, so the surface has to
stay clear of any progress UI during a capture.

Cancel is wired via a permanently-installed ``bind_all`` Escape
handler that consults a module-level list of active cancel flags —
guarded so it's a no-op when no batch is running and so tkinter's
inability to cleanly unbind one ``bind_all`` callback never bites us.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

from app.ui.zoom_controller import (
    GHOST_HINT_DANGER_FG,
    GHOST_HINT_INFO_FG,
    GHOST_HINT_WARN_FG,
)

if TYPE_CHECKING:
    from app.ui.workspace.core import Workspace


# First doc needs a longer settle for Tk to lay out the freshly-focused
# rectangle; subsequent docs reuse the same canvas + scroll machinery
# and capture cleanly with a shorter wait.
_FIRST_SETTLE_MS = 150
_SETTLE_MS = 80

# Active batches register a ``{"value": False}`` cancel flag here.
# The shared Escape handler flips every registered flag — supports
# concurrent / nested batches (theoretical; today the click is
# guarded against re-entry) without per-batch bind/unbind churn.
_active_cancel_flags: list[dict] = []
_escape_bound: bool = False


def _on_escape(_event: tk.Event) -> None:
    for flag in _active_cancel_flags:
        flag["value"] = True


def _ensure_escape_bound(workspace: "Workspace") -> None:
    global _escape_bound
    if _escape_bound:
        return
    workspace.winfo_toplevel().bind_all(
        "<Escape>", _on_escape, add="+",
    )
    _escape_bound = True


def _pick_colour(live_count: int) -> str:
    """Match the banner's severity colour so progress reads in the
    same key the user just clicked from."""
    if live_count >= 10:
        return GHOST_HINT_DANGER_FG
    if live_count >= 3:
        return GHOST_HINT_WARN_FG
    return GHOST_HINT_INFO_FG


def _pick_attention_doc(workspace: "Workspace", live: list):
    """Return the doc to leave alive during a bulk-ghost. Active doc
    wins when any portion of it sits in the viewport; otherwise the
    doc with the largest visible area takes over (handles the case
    where the user scrolled away from ``active_document_id`` and is
    looking at something else). Falls back to the active / first live
    doc when nothing is visible at all so the user still lands on a
    sensible target after the batch completes.
    """
    from app.ui.workspace.render import DOCUMENT_PADDING
    canvas = workspace.canvas
    workspace.update_idletasks()
    zoom = workspace.zoom.canvas_scale
    pad = DOCUMENT_PADDING
    view_w = canvas.winfo_width() or 800
    view_h = canvas.winfo_height() or 600
    try:
        vx0 = int(canvas.canvasx(0))
        vy0 = int(canvas.canvasy(0))
    except tk.TclError:
        return live[0]
    vx1 = vx0 + view_w
    vy1 = vy0 + view_h

    def visible_area(doc) -> int:
        x0 = pad + int(doc.canvas_x * zoom)
        y0 = pad + int(doc.canvas_y * zoom)
        x1 = x0 + max(1, int(doc.width * zoom))
        y1 = y0 + max(1, int(doc.height * zoom))
        iw = max(0, min(x1, vx1) - max(x0, vx0))
        ih = max(0, min(y1, vy1) - max(y0, vy0))
        return iw * ih

    active_id = workspace.project.active_document_id
    active_doc = next((d for d in live if d.id == active_id), None)
    if active_doc is not None and visible_area(active_doc) > 0:
        return active_doc
    best = max(live, key=visible_area)
    if visible_area(best) > 0:
        return best
    return active_doc or live[0]


def ghost_all_live_docs(workspace: "Workspace") -> None:
    project = workspace.project
    # Mirror ``_count_live_docs`` — skip empty docs so the batch
    # doesn't waste time freezing rectangles with nothing in them.
    live = [
        d for d in project.documents
        if not d.ghosted and not d.collapsed and d.root_widgets
    ]
    if len(live) < 2:
        return

    # One doc stays alive — the one the user is currently looking at
    # (active doc when visible, else the most-visible). Without this
    # the batch ghosts every doc including the one we re-focus at the
    # end, leaving the user staring at a centered screenshot of what
    # they were just editing.
    attention = _pick_attention_doc(workspace, live)
    targets = [d for d in live if d.id != attention.id]
    if not targets:
        return

    root = workspace.winfo_toplevel()
    colour = _pick_colour(len(targets))

    cancelled = {"value": False}
    _active_cancel_flags.append(cancelled)
    _ensure_escape_bound(workspace)

    zoom = workspace.zoom
    zoom.begin_batch(
        f"      Ghosting 0 / {len(targets)} — preparing...  (Esc to cancel)",
        colour,
    )
    root.update()

    failures: list[str] = []
    try:
        for i, doc in enumerate(targets):
            if cancelled["value"]:
                break
            try:
                workspace.focus_document(doc.id)
                project.set_active_document(doc.id)
                root.update()
                root.after(_FIRST_SETTLE_MS if i == 0 else _SETTLE_MS)
                root.update()
                project.set_document_ghost(doc.id, True)
            except Exception:
                logging.exception(
                    "[ghost-all] failed for doc %s", doc.id,
                )
                failures.append(doc.id)
            zoom.set_batch_text(
                f"      Ghosting {i + 1} / {len(targets)} — "
                f"{doc.name[:40]}  (Esc to cancel)",
            )
            root.update()
    finally:
        try:
            _active_cancel_flags.remove(cancelled)
        except ValueError:
            pass
        if project.get_document(attention.id) is not None:
            project.set_active_document(attention.id)
            workspace.focus_document(attention.id)
        zoom.end_batch()

    if failures:
        logging.warning(
            "[ghost-all] completed with %d failure(s): %s",
            len(failures), ", ".join(failures),
        )
    elif cancelled["value"]:
        logging.info("[ghost-all] cancelled by user")
    else:
        logging.info("[ghost-all] ghosted %d docs", len(live))
