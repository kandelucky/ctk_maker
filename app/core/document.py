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

from app.core.object_references import ObjectReferenceEntry
from app.core.variables import VariableEntry
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
    # Builder-only drag aids. Both default ON; legacy projects use
    # ``.get(key, True)`` at consumption sites so missing keys keep
    # the original behaviour.
    "alignment_lines_enabled": True,
    "snap_enabled": True,
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
        # Builder-only — when True the document is hidden from the
        # canvas (no rect, no chrome, no widget instantiation) and
        # surfaces as a small tab in the canvas bottom-left strip.
        # Persisted so the layout survives reload; widgets are only
        # built lazily when the user expands the doc again.
        self.collapsed: bool = False
        # Builder-only — when True the document's live widgets are
        # destroyed and replaced with a desaturated PIL screenshot
        # placed on the workspace canvas at the same canvas_x / y.
        # Frees up Tk event/render cost for inactive forms while
        # keeping a visible placeholder; ghost auto-disables on the
        # currently-active doc (set_document_ghost demotes it).
        self.ghosted: bool = False
        self.root_widgets: list[WidgetNode] = []
        # AI-bridge meta-property for the window itself. Mirror of
        # ``WidgetNode.description`` — emitted as Python comments above
        # the generated ``class X(ctk.CTk):`` line at export time.
        self.description: str = ""
        # Per-document shared variables (Phase 1.5 visual scripting).
        # Visible only to widgets inside this document; cross-document
        # bindings are blocked by the Properties panel and refused at
        # export time. Globals live on ``Project.variables`` instead.
        self.local_variables: list[VariableEntry] = []
        # Per-document monotonic counter for auto-naming new widgets
        # ("Button", "Button (1)", "Button (2)", …). Kept per-document
        # so numbering restarts inside each Dialog and every fresh
        # project. Not persisted — load_project rebuilds it from
        # existing widget names.
        self.name_counters: dict[str, int] = {}
        # v1.10.8 Object References — local scope holds ``ref[Widget]``
        # slots whose target lives inside this document. Globals
        # (``ref[Window]`` / ``ref[Dialog]``) live on
        # ``Project.object_references`` instead. The Variables window
        # and Properties panel both work against this list; the code
        # exporter consumes it to emit ``self._behavior.<name>``
        # assignments after ``_build_ui()``.
        self.local_object_references: list[ObjectReferenceEntry] = []

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        result = {
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
        if self.collapsed:
            result["collapsed"] = True
        if self.ghosted:
            result["ghosted"] = True
        if self.description:
            result["description"] = self.description
        if self.local_variables:
            result["local_variables"] = [
                v.to_dict() for v in self.local_variables
            ]
        if self.local_object_references:
            result["local_object_references"] = [
                r.to_dict() for r in self.local_object_references
            ]
        return result

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
        doc.collapsed = bool(data.get("collapsed", False))
        # Ghost state has to be deferred — applying it before widgets
        # are built would skip their creation, leaving nothing to
        # screenshot. The post-load pass on the workspace consumes
        # ``_pending_ghost`` to freeze each saved-ghost doc once
        # widgets are alive on the canvas.
        doc.ghosted = False
        doc._pending_ghost = bool(data.get("ghosted", False))
        raw_desc = data.get("description")
        if isinstance(raw_desc, str):
            doc.description = raw_desc
        raw_locals = data.get("local_variables")
        if isinstance(raw_locals, list):
            for raw_var in raw_locals:
                if not isinstance(raw_var, dict):
                    continue
                entry = VariableEntry.from_dict(raw_var)
                # Force scope = "local" defensively in case the saved
                # payload is missing or wrong; the storage location is
                # the source of truth here.
                entry.scope = "local"
                doc.local_variables.append(entry)
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
        raw_refs = data.get("local_object_references")
        if isinstance(raw_refs, list):
            for raw in raw_refs:
                if not isinstance(raw, dict):
                    continue
                entry = ObjectReferenceEntry.from_dict(raw)
                entry.scope = "local"
                doc.local_object_references.append(entry)
        # v1.10.7- legacy migration: a ``behavior_field_values`` dict in
        # the JSON payload predates Object References. Convert each
        # entry to a local ObjectReferenceEntry with target_type
        # defaulting to ``CTkLabel`` (the JSON didn't carry type info).
        # Skipped when an entry with the same name already exists in
        # ``local_object_references`` so a partial-migration replay is
        # idempotent. The next save drops the legacy key naturally
        # because ``to_dict`` no longer emits it.
        raw_legacy = data.get("behavior_field_values")
        if isinstance(raw_legacy, dict):
            existing_names = {
                r.name for r in doc.local_object_references
            }
            for raw_name, raw_widget_id in raw_legacy.items():
                if not isinstance(raw_name, str) or not raw_name:
                    continue
                if not isinstance(raw_widget_id, str):
                    continue
                if raw_name in existing_names:
                    continue
                doc.local_object_references.append(
                    ObjectReferenceEntry(
                        name=raw_name,
                        target_type="CTkLabel",
                        scope="local",
                        target_id=raw_widget_id,
                    ),
                )
                existing_names.add(raw_name)
        return doc
