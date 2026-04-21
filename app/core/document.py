"""Document — a single form / window inside a project.

Phase 5.5 introduces multi-document projects: one ``.ctkproj`` can
hold a main window plus any number of dialogs / toplevels, all
editable on the same canvas. Each ``Document`` owns its own size,
window properties, root widget tree, and canvas placement.

Project.documents is a list of these; ``project.active_document``
is the one receiving new drops / menu actions. Selection, history,
and save/load all key off the individual document's state.
"""
from __future__ import annotations

import uuid

from app.core.widget_node import WidgetNode

# Defaults for a freshly-created Document. Mirrors the previous
# Project-level constants so single-document projects round-trip
# unchanged through the migration layer.
DEFAULT_DOCUMENT_WIDTH = 800
DEFAULT_DOCUMENT_HEIGHT = 600

DEFAULT_WINDOW_PROPERTIES = {
    "fg_color": "transparent",
    "resizable_x": True,
    "resizable_y": True,
    "frameless": False,
    # Builder-only — the grid is a design-time helper, never makes
    # it into the exported Python code. Stored here so each
    # document can carry its own style + colour.
    "grid_style": "dots",
    "grid_color": "#555555",
    "grid_spacing": 20,
    # Tk geometry manager used for the window's direct children at
    # export time. Canvas always positions widgets by absolute x/y
    # in the editor — this only changes the .py output.
    "layout_type": "place",
}


class Document:
    def __init__(
        self,
        name: str = "Main Window",
        width: int = DEFAULT_DOCUMENT_WIDTH,
        height: int = DEFAULT_DOCUMENT_HEIGHT,
        canvas_x: int = 0,
        canvas_y: int = 0,
        window_properties: dict | None = None,
        is_toplevel: bool = False,
        color: str | None = None,
    ):
        self.id: str = str(uuid.uuid4())
        self.name: str = name
        # User-picked accent colour. ``None`` means use the palette
        # cycle (see ``Project.get_accent_color``). Set via the
        # Window Settings dialog.
        self.color: str | None = color
        self.width: int = int(width)
        self.height: int = int(height)
        # Canvas offset — where the document's top-left sits inside
        # the shared workspace canvas. The first document lives at
        # (0, 0); additional documents get placed to the right so
        # they don't overlap on creation.
        self.canvas_x: int = int(canvas_x)
        self.canvas_y: int = int(canvas_y)
        self.window_properties: dict = (
            dict(window_properties) if window_properties
            else dict(DEFAULT_WINDOW_PROPERTIES)
        )
        # True when this document represents a CTkToplevel rather
        # than the CTk main window — drives the exporter's class
        # signature (``class X(ctk.CTk):`` vs ``ctk.CTkToplevel``).
        self.is_toplevel: bool = bool(is_toplevel)
        self.root_widgets: list[WidgetNode] = []
        # Per-document monotonic counter for auto-naming new widgets
        # ("Button", "Button (1)", "Button (2)", …). Kept per-document
        # so numbering restarts inside each Dialog and every fresh
        # project. Not persisted — load_project rebuilds it from
        # existing widget names.
        self.name_counters: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "width": self.width,
            "height": self.height,
            "canvas_x": self.canvas_x,
            "canvas_y": self.canvas_y,
            "window_properties": dict(self.window_properties),
            "is_toplevel": self.is_toplevel,
            "widgets": [w.to_dict() for w in self.root_widgets],
            "name_counters": dict(self.name_counters),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        raw_color = data.get("color")
        doc = cls(
            name=str(data.get("name") or "Main Window"),
            width=int(data.get("width", DEFAULT_DOCUMENT_WIDTH)),
            height=int(data.get("height", DEFAULT_DOCUMENT_HEIGHT)),
            canvas_x=int(data.get("canvas_x", 0)),
            canvas_y=int(data.get("canvas_y", 0)),
            window_properties=data.get("window_properties"),
            is_toplevel=bool(data.get("is_toplevel", False)),
            color=raw_color if isinstance(raw_color, str) else None,
        )
        raw_id = data.get("id")
        if isinstance(raw_id, str) and raw_id:
            doc.id = raw_id
        for raw in data.get("widgets", []):
            if not isinstance(raw, dict):
                continue
            node = WidgetNode.from_dict(raw)
            node.parent = None
            doc.root_widgets.append(node)
        # Restore per-document auto-name counters if the saved file
        # has them (v0.0.15.17+). Older files fall back to 0 — first
        # new widget after open reuses a base name, which was the
        # behaviour users already observed on legacy projects.
        raw_counters = data.get("name_counters")
        if isinstance(raw_counters, dict):
            doc.name_counters = {
                str(k): int(v) for k, v in raw_counters.items()
                if isinstance(v, (int, float))
            }
        return doc
