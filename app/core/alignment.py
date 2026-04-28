"""Alignment + distribution math for the widget canvas.

Pure functions — no Tk, no Project state mutations. Each entry
point takes the widgets to operate on plus the container's bounds
(or ``None`` when aligning to the selection's own bounding box) and
returns a list of ``(widget_id, before_dict, after_dict)`` tuples
the caller passes straight to ``BulkMoveCommand``.

Reference frame: every widget's ``properties["x"]`` / ``["y"]`` is
the top-left corner inside its parent. Widget size comes from
``properties["width"]`` / ``["height"]``. Layout-managed children
(parent ``layout_type`` ∈ {vbox, hbox, grid}) are filtered out by
the caller — alignment doesn't apply when the layout manager owns
positioning.

Modes:
    "left" / "center_h" / "right"  — horizontal alignment (X)
    "top"  / "center_v" / "bottom" — vertical alignment (Y)
    "distribute_h" / "distribute_v" — equal spacing (3+ widgets)

Anchor logic when aligning to selection bbox:
    - left   → leftmost widget's x stays put; others snap to it
    - right  → rightmost widget's right edge stays put; others snap
    - center → midpoint of selection bbox
    Same shape on the vertical axis.
"""

from __future__ import annotations

from typing import Iterable

# Sentinel modes — string keys make the toolbar wiring trivial
# (one dict lookup) without exposing an enum class to every caller.
MODE_LEFT = "left"
MODE_CENTER_H = "center_h"
MODE_RIGHT = "right"
MODE_TOP = "top"
MODE_CENTER_V = "center_v"
MODE_BOTTOM = "bottom"
MODE_DISTRIBUTE_H = "distribute_h"
MODE_DISTRIBUTE_V = "distribute_v"

ALIGN_MODES = frozenset({
    MODE_LEFT, MODE_CENTER_H, MODE_RIGHT,
    MODE_TOP, MODE_CENTER_V, MODE_BOTTOM,
})
DISTRIBUTE_MODES = frozenset({MODE_DISTRIBUTE_H, MODE_DISTRIBUTE_V})


def _xywh(node) -> tuple[int, int, int, int]:
    """Pull (x, y, width, height) from a node's properties as ints.
    Missing values fall back to 0 — matches what render code does
    when a property hasn't been set yet.
    """
    p = node.properties or {}
    return (
        int(p.get("x", 0) or 0),
        int(p.get("y", 0) or 0),
        int(p.get("width", 0) or 0),
        int(p.get("height", 0) or 0),
    )


def _selection_bbox(nodes: Iterable) -> tuple[int, int, int, int]:
    """Smallest rectangle containing every widget. Returns
    (left, top, right, bottom) in parent-local coordinates."""
    xs1, ys1, xs2, ys2 = [], [], [], []
    for n in nodes:
        x, y, w, h = _xywh(n)
        xs1.append(x)
        ys1.append(y)
        xs2.append(x + w)
        ys2.append(y + h)
    return min(xs1), min(ys1), max(xs2), max(ys2)


def compute_align(
    nodes: list,
    mode: str,
    container_size: tuple[int, int] | None = None,
) -> list[tuple[str, dict, dict]]:
    """Build the move list for an align action.

    ``nodes`` — widgets to operate on (must share the same parent
    coordinate space; the caller filters cross-parent selections).
    ``mode`` — one of the ``MODE_*`` constants in ``ALIGN_MODES``.
    ``container_size`` — ``(width, height)`` of the parent (Window
    or container Frame) when aligning a single selected widget to
    its container; ``None`` when aligning to the selection's own
    bounding box.

    Returns a list of ``(widget_id, before, after)`` tuples for
    BulkMoveCommand. Widgets that don't move are still included
    with identical before/after — keeps the command count stable
    so undo always rewinds the same widgets the user saw flash.
    Returns ``[]`` when ``nodes`` is empty or mode is unknown.
    """
    if not nodes or mode not in ALIGN_MODES:
        return []
    if container_size is not None:
        cw, ch = container_size
        # Container-relative target: derive from container bounds.
        # selection_bbox isn't needed in this branch.
        return _moves_to_container(nodes, mode, cw, ch)
    # Selection-relative target: derive from selection bbox.
    return _moves_to_selection(nodes, mode)


def _moves_to_container(
    nodes: list, mode: str, cw: int, ch: int,
) -> list[tuple[str, dict, dict]]:
    moves: list[tuple[str, dict, dict]] = []
    for n in nodes:
        x, y, w, h = _xywh(n)
        new_x, new_y = x, y
        if mode == MODE_LEFT:
            new_x = 0
        elif mode == MODE_RIGHT:
            new_x = max(0, cw - w)
        elif mode == MODE_CENTER_H:
            new_x = max(0, (cw - w) // 2)
        elif mode == MODE_TOP:
            new_y = 0
        elif mode == MODE_BOTTOM:
            new_y = max(0, ch - h)
        elif mode == MODE_CENTER_V:
            new_y = max(0, (ch - h) // 2)
        before = {"x": x, "y": y}
        after = {"x": new_x, "y": new_y}
        moves.append((n.id, before, after))
    return moves


def _moves_to_selection(
    nodes: list, mode: str,
) -> list[tuple[str, dict, dict]]:
    bbox_l, bbox_t, bbox_r, bbox_b = _selection_bbox(nodes)
    moves: list[tuple[str, dict, dict]] = []
    for n in nodes:
        x, y, w, h = _xywh(n)
        new_x, new_y = x, y
        if mode == MODE_LEFT:
            new_x = bbox_l
        elif mode == MODE_RIGHT:
            new_x = bbox_r - w
        elif mode == MODE_CENTER_H:
            new_x = ((bbox_l + bbox_r) - w) // 2
        elif mode == MODE_TOP:
            new_y = bbox_t
        elif mode == MODE_BOTTOM:
            new_y = bbox_b - h
        elif mode == MODE_CENTER_V:
            new_y = ((bbox_t + bbox_b) - h) // 2
        before = {"x": x, "y": y}
        after = {"x": new_x, "y": new_y}
        moves.append((n.id, before, after))
    return moves


def compute_distribute(
    nodes: list, mode: str,
) -> list[tuple[str, dict, dict]]:
    """Build the move list for a distribute action.

    Needs at least 3 widgets — with 2 you'd just be aligning their
    centers, which the user can already get from compute_align.

    The two outermost widgets stay put; intermediate widgets get
    repositioned so the gaps between consecutive bounding boxes
    are equal. "Gap" = right-edge of N to left-edge of N+1, so
    widgets of different sizes still distribute evenly visually.

    ``mode`` is ``MODE_DISTRIBUTE_H`` or ``MODE_DISTRIBUTE_V``.
    Returns ``[]`` if mode unknown or fewer than 3 nodes.
    """
    if mode not in DISTRIBUTE_MODES or len(nodes) < 3:
        return []
    horizontal = mode == MODE_DISTRIBUTE_H
    # Sort by axis-relevant coordinate so "first" / "last" are the
    # visual extremes the user sees, not the order they happened
    # to be selected in.
    if horizontal:
        ordered = sorted(nodes, key=lambda n: _xywh(n)[0])
    else:
        ordered = sorted(nodes, key=lambda n: _xywh(n)[1])

    # Total span = far edge of last - near edge of first; total
    # widget extent = sum of sizes. The remaining space splits
    # evenly into N-1 gaps.
    fx, fy, fw, fh = _xywh(ordered[0])
    lx, ly, lw, lh = _xywh(ordered[-1])
    if horizontal:
        span = (lx + lw) - fx
        total_size = sum(_xywh(n)[2] for n in ordered)
    else:
        span = (ly + lh) - fy
        total_size = sum(_xywh(n)[3] for n in ordered)
    free = span - total_size
    if free < 0:
        # Widgets overlap the available range; flat distribution
        # would push them past each other. Bail out cleanly.
        return [(n.id, _bare_pos(n), _bare_pos(n)) for n in ordered]
    gap = free // (len(ordered) - 1)

    moves: list[tuple[str, dict, dict]] = []
    cursor = (fx if horizontal else fy)
    for i, n in enumerate(ordered):
        x, y, w, h = _xywh(n)
        if horizontal:
            new_x = cursor if i not in (0, len(ordered) - 1) else x
            new_y = y
            cursor += w + gap
        else:
            new_x = x
            new_y = cursor if i not in (0, len(ordered) - 1) else y
            cursor += h + gap
        moves.append((
            n.id, {"x": x, "y": y}, {"x": new_x, "y": new_y},
        ))
    return moves


def _bare_pos(node) -> dict:
    x, y, _w, _h = _xywh(node)
    return {"x": x, "y": y}


def _unit_bbox(unit: list) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of a unit (one or more widgets that
    move together). For a single-widget unit this is just its rect;
    for a multi-widget unit it's the union of every member's rect."""
    return _selection_bbox(unit)


def compute_align_units(
    units: list,
    mode: str,
    container_size: tuple[int, int] | None = None,
) -> list[tuple[str, dict, dict]]:
    """Group-aware variant of ``compute_align``. Each ``unit`` is a
    list of widget nodes that should move together as one block — a
    selected group becomes a single multi-widget unit, an ungrouped
    selection becomes a singleton. Alignment math runs on each unit's
    combined bbox; the resulting offset is applied to every member.
    """
    if not units or mode not in ALIGN_MODES:
        return []
    if container_size is not None:
        cw, ch = container_size
        return _unit_moves_to_container(units, mode, cw, ch)
    return _unit_moves_to_selection(units, mode)


def _unit_moves_to_container(
    units: list, mode: str, cw: int, ch: int,
) -> list[tuple[str, dict, dict]]:
    moves: list[tuple[str, dict, dict]] = []
    for unit in units:
        bl, bt, br, bb = _unit_bbox(unit)
        bw, bh = br - bl, bb - bt
        new_l, new_t = bl, bt
        if mode == MODE_LEFT:
            new_l = 0
        elif mode == MODE_RIGHT:
            new_l = max(0, cw - bw)
        elif mode == MODE_CENTER_H:
            new_l = max(0, (cw - bw) // 2)
        elif mode == MODE_TOP:
            new_t = 0
        elif mode == MODE_BOTTOM:
            new_t = max(0, ch - bh)
        elif mode == MODE_CENTER_V:
            new_t = max(0, (ch - bh) // 2)
        dx, dy = new_l - bl, new_t - bt
        moves.extend(_apply_offset(unit, dx, dy))
    return moves


def _unit_moves_to_selection(
    units: list, mode: str,
) -> list[tuple[str, dict, dict]]:
    # Outer bbox = union over UNIT bboxes (not individual widgets) so
    # leftmost/rightmost reference is the leftmost/rightmost UNIT.
    unit_rects = [_unit_bbox(u) for u in units]
    bbox_l = min(r[0] for r in unit_rects)
    bbox_t = min(r[1] for r in unit_rects)
    bbox_r = max(r[2] for r in unit_rects)
    bbox_b = max(r[3] for r in unit_rects)
    moves: list[tuple[str, dict, dict]] = []
    for unit, (ul, ut, ur, ub) in zip(units, unit_rects):
        uw, uh = ur - ul, ub - ut
        new_l, new_t = ul, ut
        if mode == MODE_LEFT:
            new_l = bbox_l
        elif mode == MODE_RIGHT:
            new_l = bbox_r - uw
        elif mode == MODE_CENTER_H:
            new_l = ((bbox_l + bbox_r) - uw) // 2
        elif mode == MODE_TOP:
            new_t = bbox_t
        elif mode == MODE_BOTTOM:
            new_t = bbox_b - uh
        elif mode == MODE_CENTER_V:
            new_t = ((bbox_t + bbox_b) - uh) // 2
        dx, dy = new_l - ul, new_t - ut
        moves.extend(_apply_offset(unit, dx, dy))
    return moves


def _apply_offset(
    unit: list, dx: int, dy: int,
) -> list[tuple[str, dict, dict]]:
    out: list[tuple[str, dict, dict]] = []
    for n in unit:
        x, y, _w, _h = _xywh(n)
        before = {"x": x, "y": y}
        after = {"x": x + dx, "y": y + dy}
        out.append((n.id, before, after))
    return out


def compute_distribute_units(
    units: list, mode: str,
) -> list[tuple[str, dict, dict]]:
    """Group-aware variant of ``compute_distribute``. Operates on
    UNIT bboxes (a selected group counts as one block) so distributing
    one group with two ungrouped widgets yields three evenly-spaced
    bboxes rather than spacing every group member individually.
    Needs at least 3 units.
    """
    if mode not in DISTRIBUTE_MODES or len(units) < 3:
        return []
    horizontal = mode == MODE_DISTRIBUTE_H
    unit_rects = [_unit_bbox(u) for u in units]
    if horizontal:
        order = sorted(
            range(len(units)), key=lambda i: unit_rects[i][0],
        )
    else:
        order = sorted(
            range(len(units)), key=lambda i: unit_rects[i][1],
        )
    ordered_units = [units[i] for i in order]
    ordered_rects = [unit_rects[i] for i in order]
    fl, ft, fr, fb = ordered_rects[0]
    ll, lt, lr, lb = ordered_rects[-1]
    if horizontal:
        span = lr - fl
        total_size = sum(r[2] - r[0] for r in ordered_rects)
    else:
        span = lb - ft
        total_size = sum(r[3] - r[1] for r in ordered_rects)
    free = span - total_size
    if free < 0:
        # Units overlap the available range — can't distribute cleanly.
        out: list[tuple[str, dict, dict]] = []
        for unit in ordered_units:
            out.extend(_apply_offset(unit, 0, 0))
        return out
    gap = free // (len(ordered_units) - 1)
    moves: list[tuple[str, dict, dict]] = []
    cursor = fl if horizontal else ft
    for i, (unit, rect) in enumerate(zip(ordered_units, ordered_rects)):
        ul, ut, ur, ub = rect
        uw, uh = ur - ul, ub - ut
        if i in (0, len(ordered_units) - 1):
            new_l, new_t = ul, ut  # endpoints stay put
        elif horizontal:
            new_l, new_t = cursor, ut
        else:
            new_l, new_t = ul, cursor
        dx, dy = new_l - ul, new_t - ut
        moves.extend(_apply_offset(unit, dx, dy))
        cursor += (uw if horizontal else uh) + gap
    return moves
