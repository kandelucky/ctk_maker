"""Snap + alignment guide math for the drag controller.

Pure functions — no Tk, no Project mutations. Drag motion calls
``compute_snap_offsets`` with the would-be position of the primary
dragging widget, plus the sibling widgets it should align against.
The function returns ``(snap_dx, snap_dy, guide_positions)`` —
``snap_dx``/``snap_dy`` are the fractional shifts that move the
widget's edges onto the closest sibling/container reference within
the threshold; ``guide_positions`` is what the canvas draws as the
pink guide lines while the gesture is alive.

Snap targets along each axis:
    - container edges: ``0`` and ``container_size``
    - container center: ``container_size // 2``
    - per sibling: left / center / right (X axis)
                   top / center / bottom (Y axis)

Three reference points on the dragging widget itself: its near edge,
its centre, and its far edge. The closest pair (any-edge × any-target)
within the threshold wins; ties favour edges over centres.
"""

from __future__ import annotations

DEFAULT_THRESHOLD_PX = 5


def _axis_targets(
    sibling_ranges: list[tuple[int, int]],
    container_size: int | None,
) -> list[int]:
    """Build the list of snap-target positions along one axis.

    ``sibling_ranges`` — list of ``(near_edge, far_edge)`` per sibling
    (e.g. (left, right) for the X axis).
    ``container_size`` — total span of the parent along this axis;
    contributes 0, half-span, and full-span as targets when given.
    """
    targets: list[int] = []
    if container_size is not None:
        targets.extend((0, container_size // 2, container_size))
    for near, far in sibling_ranges:
        targets.extend((near, (near + far) // 2, far))
    return targets


def _best_snap(
    drag_min: int, drag_size: int,
    targets: list[int], threshold: int,
) -> tuple[int, list[int]]:
    """Find the offset that aligns one of the dragging widget's
    three reference points (near / centre / far) to the nearest
    target within ``threshold``.

    Returns ``(offset, matched_target_positions)``. ``offset == 0``
    when nothing snaps; ``matched`` is empty in that case. When
    snap fires, ``matched`` is every target that the post-snap
    position lands on (multiple references may hit the same line).
    """
    drag_center = drag_min + drag_size // 2
    drag_max = drag_min + drag_size
    drag_points = (drag_min, drag_center, drag_max)
    best_offset = 0
    best_dist = threshold + 1
    for target in targets:
        for dp in drag_points:
            dist = target - dp
            if abs(dist) < abs(best_dist):
                best_dist = dist
                best_offset = dist
    if abs(best_dist) > threshold:
        return 0, []
    # Snap commits — figure out which targets the new edge / centre /
    # far lands on so the guide drawer can render every matching line.
    new_min = drag_min + best_offset
    new_center = new_min + drag_size // 2
    new_max = new_min + drag_size
    new_points = {new_min, new_center, new_max}
    matched = sorted({t for t in targets if t in new_points})
    return best_offset, matched


def compute_snap_offsets(
    dragging_bbox: tuple[int, int, int, int],
    sibling_bboxes: list[tuple[int, int, int, int]],
    container_size: tuple[int, int] | None = None,
    threshold: int = DEFAULT_THRESHOLD_PX,
) -> tuple[int, int, list[int], list[int]]:
    """Compute snap adjustments along both axes for one dragging
    widget.

    ``dragging_bbox`` — ``(x, y, x + w, y + h)`` in parent-local
    coordinates (same space as the snap targets).
    ``sibling_bboxes`` — list of bounding boxes for siblings the
    dragging widget should consider snap targets against.
    ``container_size`` — ``(width, height)`` of the dragging widget's
    parent; used to add container edges + centre as targets.

    Returns ``(snap_dx, snap_dy, guide_xs, guide_ys)``:
      - ``snap_dx``/``snap_dy`` — apply to the dragging widget's
        x/y to land on the snap.
      - ``guide_xs`` — vertical guide X positions to draw.
      - ``guide_ys`` — horizontal guide Y positions to draw.
    """
    x1, y1, x2, y2 = dragging_bbox
    w = x2 - x1
    h = y2 - y1

    cw = container_size[0] if container_size else None
    ch = container_size[1] if container_size else None

    x_targets = _axis_targets(
        [(b[0], b[2]) for b in sibling_bboxes], cw,
    )
    y_targets = _axis_targets(
        [(b[1], b[3]) for b in sibling_bboxes], ch,
    )

    snap_dx, guide_xs = _best_snap(x1, w, x_targets, threshold)
    snap_dy, guide_ys = _best_snap(y1, h, y_targets, threshold)
    return snap_dx, snap_dy, guide_xs, guide_ys
