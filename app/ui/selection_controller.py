import tkinter as tk
from typing import Callable

HANDLE_NAMES = ("nw", "n", "ne", "w", "e", "sw", "s", "se")
HANDLE_SIZE = 8
HANDLE_FILL = "#3b8ed0"
HANDLE_OUTLINE = "#ffffff"
SELECTION_PAD = 6
MIN_WIDGET_SIZE = 20

HANDLE_CURSORS = {
    "nw": "size_nw_se",
    "n":  "sb_v_double_arrow",
    "ne": "size_ne_sw",
    "w":  "sb_h_double_arrow",
    "e":  "sb_h_double_arrow",
    "sw": "size_ne_sw",
    "s":  "sb_v_double_arrow",
    "se": "size_nw_se",
}

HANDLE_OFFSETS = {
    "nw": (-1, -1), "n":  (0, -1), "ne": (1, -1),
    "w":  (-1,  0),               "e":  (1,  0),
    "sw": (-1,  1), "s":  (0,  1), "se": (1,  1),
}


class SelectionController:
    def __init__(
        self,
        canvas: tk.Canvas,
        project,
        widget_views: dict,
        zoom_provider: Callable[[], float] = lambda: 1.0,
    ):
        self.canvas = canvas
        self.project = project
        self.widget_views = widget_views
        self._zoom_provider = zoom_provider
        self._selection_rect: int | None = None
        self._handle_ids: dict[str, int] = {}
        self._resize: dict | None = None

    def is_resizing(self) -> bool:
        return self._resize is not None

    def draw(self) -> None:
        bbox = self._selected_bbox()
        if bbox is None:
            self.clear()
            return
        self.clear()
        self._create(*bbox)

    def update(self) -> None:
        if self._selection_rect is None:
            self.draw()
            return
        bbox = self._selected_bbox()
        if bbox is None:
            return
        self._update_coords(*bbox)

    def clear(self) -> None:
        if self._selection_rect is not None:
            self.canvas.delete(self._selection_rect)
            self._selection_rect = None
        for item_id in self._handle_ids.values():
            self.canvas.delete(item_id)
        self._handle_ids = {}

    def handle_at(self, x: int, y: int) -> str | None:
        for name, item_id in self._handle_ids.items():
            coords = self.canvas.coords(item_id)
            if not coords:
                continue
            x1, y1, x2, y2 = coords
            if x1 - 2 <= x <= x2 + 2 and y1 - 2 <= y <= y2 + 2:
                return name
        return None

    def begin_resize(self, event, handle_name: str) -> None:
        sid = self.project.selected_id
        if sid is None:
            return
        node = self.project.get_widget(sid)
        if node is None:
            return
        try:
            x = int(node.properties.get("x", 0))
            y = int(node.properties.get("y", 0))
            w = int(node.properties.get("width", 0))
            h = int(node.properties.get("height", 0))
        except (ValueError, TypeError):
            return
        self._resize = {
            "nid": sid, "handle": handle_name,
            "start_x": x, "start_y": y, "start_w": w, "start_h": h,
            "press_mx": event.x_root, "press_my": event.y_root,
        }

    def update_resize(self, event) -> None:
        r = self._resize
        if r is None:
            return
        zoom = self._zoom_provider() or 1.0
        dx = int((event.x_root - r["press_mx"]) / zoom)
        dy = int((event.y_root - r["press_my"]) / zoom)
        new_x, new_y, new_w, new_h = self._compute_resize(
            r["handle"], r["start_x"], r["start_y"], r["start_w"], r["start_h"],
            dx, dy,
        )
        nid = r["nid"]
        node = self.project.get_widget(nid)
        if node is None:
            return
        if int(node.properties.get("x", 0)) != new_x:
            self.project.update_property(nid, "x", new_x)
        if int(node.properties.get("y", 0)) != new_y:
            self.project.update_property(nid, "y", new_y)
        if int(node.properties.get("width", 0)) != new_w:
            self.project.update_property(nid, "width", new_w)
        if int(node.properties.get("height", 0)) != new_h:
            self.project.update_property(nid, "height", new_h)
        self.update()

    def end_resize(self, _event) -> None:
        self._resize = None
        try:
            self.canvas.configure(cursor="")
        except tk.TclError:
            pass
        self.draw()

    def _selected_bbox(self) -> tuple[int, int, int, int] | None:
        sid = self.project.selected_id
        if sid is None or sid not in self.widget_views:
            return None
        _, window_id = self.widget_views[sid]
        self.canvas.update_idletasks()
        return self.canvas.bbox(window_id)

    def _create(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self._selection_rect = self.canvas.create_rectangle(
            x1 - SELECTION_PAD, y1 - SELECTION_PAD,
            x2 + SELECTION_PAD, y2 + SELECTION_PAD,
            outline="#3b8ed0", width=2, dash=(4, 2),
        )
        half = HANDLE_SIZE // 2
        for name in HANDLE_NAMES:
            hx, hy = self._handle_center(name, x1, y1, x2, y2)
            tag = f"handle_{name}"
            item_id = self.canvas.create_rectangle(
                hx - half, hy - half, hx + half, hy + half,
                fill=HANDLE_FILL, outline=HANDLE_OUTLINE, width=1,
                tags=(tag,),
            )
            self._handle_ids[name] = item_id
            self.canvas.tag_bind(tag, "<Enter>",
                                 lambda e, n=name: self._on_handle_enter(n))
            self.canvas.tag_bind(tag, "<Leave>",
                                 lambda e, n=name: self._on_handle_leave(n))

    def _update_coords(self, x1: int, y1: int, x2: int, y2: int) -> None:
        if self._selection_rect is not None:
            self.canvas.coords(
                self._selection_rect,
                x1 - SELECTION_PAD, y1 - SELECTION_PAD,
                x2 + SELECTION_PAD, y2 + SELECTION_PAD,
            )
        half = HANDLE_SIZE // 2
        for name, item_id in self._handle_ids.items():
            hx, hy = self._handle_center(name, x1, y1, x2, y2)
            self.canvas.coords(item_id,
                               hx - half, hy - half, hx + half, hy + half)

    def _handle_center(self, name: str,
                       x1: int, y1: int, x2: int, y2: int) -> tuple[int, int]:
        ox, oy = HANDLE_OFFSETS[name]
        if ox < 0:
            cx = x1 - SELECTION_PAD
        elif ox > 0:
            cx = x2 + SELECTION_PAD
        else:
            cx = (x1 + x2) // 2
        if oy < 0:
            cy = y1 - SELECTION_PAD
        elif oy > 0:
            cy = y2 + SELECTION_PAD
        else:
            cy = (y1 + y2) // 2
        return cx, cy

    def _on_handle_enter(self, name: str) -> None:
        try:
            self.canvas.configure(cursor=HANDLE_CURSORS[name])
        except tk.TclError:
            pass

    def _on_handle_leave(self, _name: str) -> None:
        if self._resize is not None:
            return
        try:
            self.canvas.configure(cursor="")
        except tk.TclError:
            pass

    def _compute_resize(self, handle: str,
                        sx: int, sy: int, sw: int, sh: int,
                        dx: int, dy: int) -> tuple[int, int, int, int]:
        x, y, w, h = sx, sy, sw, sh
        if handle in ("nw", "w", "sw"):
            x = sx + dx
            w = sw - dx
        elif handle in ("ne", "e", "se"):
            w = sw + dx
        if handle in ("nw", "n", "ne"):
            y = sy + dy
            h = sh - dy
        elif handle in ("sw", "s", "se"):
            h = sh + dy
        if w < MIN_WIDGET_SIZE:
            if handle in ("nw", "w", "sw"):
                x = sx + sw - MIN_WIDGET_SIZE
            w = MIN_WIDGET_SIZE
        if h < MIN_WIDGET_SIZE:
            if handle in ("nw", "n", "ne"):
                y = sy + sh - MIN_WIDGET_SIZE
            h = MIN_WIDGET_SIZE
        return x, y, w, h
