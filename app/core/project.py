"""Project model — the source of truth for widgets, tree structure,
document settings, and selection state.

Phase 6.1: WidgetNodes form a parent/child tree. Top-level widgets
live in `root_widgets`; children live under their parent's
`children` list and carry a back-reference via `parent`.

Tree operations:
    add_widget(node, parent_id=None)
    remove_widget(widget_id)            — also removes its subtree
    reparent(widget_id, new_parent_id)  — move between parents
    get_widget(widget_id)               — DFS lookup
    iter_all_widgets()                  — DFS (top-down) generator

Sibling operations (work within the current parent):
    duplicate_widget, bring_to_front, send_to_back

Events published on event_bus:
    widget_added(node)                  — any add (root or child)
    widget_removed(widget_id)           — any remove
    widget_reparented(widget_id, old_parent_id, new_parent_id)
    widget_z_changed(widget_id, direction)
    property_changed(widget_id, prop_name, value)
    selection_changed(widget_id | None)
    document_resized(width, height)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    import tkinter as tk

from app.core.document import (
    DEFAULT_DOCUMENT_HEIGHT,
    DEFAULT_DOCUMENT_WIDTH,
    DEFAULT_WINDOW_PROPERTIES,
    Document,
)
from app.core.event_bus import EventBus
from app.core.history import History
from app.core.object_references import ObjectReferenceEntry
from app.core.variables import (
    VAR_TYPES,
    VariableEntry,
    coerce_default_for_type,
    is_var_token,
    make_tk_var,
    make_var_token,
    parse_var_token,
    sanitize_var_name,
)
from app.core.widget_node import WidgetNode

# Sentinel id for the virtual "Window" node that represents the
# top-level CTk window in the Object Tree + Properties panel. It's
# not stored in the widget tree and has no render — every reference
# routes through Project's window_properties accessor methods.
WINDOW_ID = "__window__"


def _walk_tree(nodes):
    """Depth-first top-down iteration over a forest of WidgetNodes."""
    stack = list(reversed(nodes))
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def find_free_cascade_slot(
    siblings, start_xy: tuple[int, int] = (10, 10),
    step: int = 20, exclude=None,
) -> tuple[int, int]:
    """Pick the first (x, y) slot among ``siblings`` that nothing
    already occupies, stepping by ``step`` pixels diagonally from
    ``start_xy``. ``exclude`` optionally skips a specific node (used
    by drag paths where the moving widget's own slot shouldn't block
    itself).

    Palette click-add, paste, tree-drag reparent, and container
    extract-to-root fallback all need the same "find next free cell"
    logic; funnel through here so the step / sampling stays
    consistent.
    """
    occupied = {
        (
            int(w.properties.get("x", 0) or 0),
            int(w.properties.get("y", 0) or 0),
        )
        for w in siblings if w is not exclude
    }
    x, y = start_xy
    while (x, y) in occupied:
        x += step
        y += step
    return x, y


class _WindowProxy:
    """Fake WidgetNode for the Window selection. Exposes the same
    surface the Object Tree + Properties panel use on real nodes —
    ``id``, ``name``, ``widget_type``, ``parent``, ``children``,
    ``visible``, ``locked``, and a ``properties`` mapping. The
    properties view always reflects current project state because
    it's a fresh dict built from live fields on every access.
    """

    __slots__ = ("_project",)

    def __init__(self, project: "Project"):
        self._project = project

    # Node-like attributes
    @property
    def id(self) -> str:
        return WINDOW_ID

    @property
    def name(self) -> str:
        return self._project.active_document.name or "Untitled"

    @property
    def widget_type(self) -> str:
        return WINDOW_ID

    @property
    def parent(self):
        return None

    @property
    def children(self) -> list:
        return []

    @property
    def visible(self) -> bool:
        return True

    @property
    def locked(self) -> bool:
        return False

    @property
    def description(self) -> str:
        # Mirror of WidgetNode.description for the active document.
        # Stored on Document so it persists with the project file.
        doc = self._project.active_document
        return getattr(doc, "description", "") if doc is not None else ""

    @description.setter
    def description(self, value: str) -> None:
        doc = self._project.active_document
        if doc is not None:
            doc.description = value or ""

    @property
    def properties(self) -> dict:
        project = self._project
        wp = project.window_properties
        # Build a fresh dict every call so Properties panel reads
        # always see live state. Every key in DEFAULT_WINDOW_PROPERTIES
        # must appear here (including grid_*), otherwise the panel's
        # property rows render with a None value and the overlays
        # look blank.
        result: dict = {
            "width": project.document_width,
            "height": project.document_height,
        }
        for key, default in DEFAULT_WINDOW_PROPERTIES.items():
            result[key] = wp.get(key, default)
        # accent_color — user override or derived palette pick. Always
        # resolves to a concrete hex string so the properties panel's
        # colour swatch has something to render.
        doc = project.active_document
        if doc is not None:
            result["accent_color"] = doc.color or project.get_accent_color(doc.id)
        return result

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "widget_type": self.widget_type,
            "properties": self.properties,
            "visible": True,
            "locked": False,
            "children": [],
        }


class Project:
    def __init__(self):
        self.event_bus = EventBus()
        # `selected_id` is the "primary" / most-recently-clicked
        # selected widget (what handles resize / property editing).
        # `selected_ids` is the full set — only relevant while the
        # Object Tree has a multi-selection active. Workspace and
        # properties panel stay single-select-aware; they see a
        # `selection_changed(None)` event when multi is active.
        self.selected_id: str | None = None
        self.selected_ids: set[str] = set()
        # Phase 5.5: a project holds a LIST of documents (forms).
        # Single-document projects keep the one default document;
        # ``active_document_id`` drives legacy ``root_widgets`` /
        # ``document_width`` / ``window_properties`` accessors for
        # code paths that haven't been ported to multi-doc yet.
        #
        # Default doc name = project name (``Untitled`` until the New
        # dialog overwrites both). Runtime ``self.title(...)`` in the
        # exported .py ends up as the project name, not a generic
        # "Main Window" that confuses users into thinking the field is
        # just an editor label.
        self.name: str = "Untitled"
        # Disk path of the currently-loaded ``.ctkproj``, or ``None``
        # while the project is fresh and unsaved. Mirrored from
        # MainWindow's ``_current_path`` via ``set_path()``; needed by
        # the asset system (token <-> absolute path resolution) and
        # by anything that wants to compute paths inside the project
        # folder without reaching into MainWindow.
        self.path: str | None = None
        # Multi-page project bookkeeping (P1). When the project is
        # loaded as a folder with ``project.json``, ``folder_path``
        # is the absolute path to that folder, ``pages`` is the
        # ordered list of page metadata dicts (``{id, file, name}``),
        # and ``active_page_id`` is the page currently in memory.
        # Legacy single-file projects leave all three at ``None`` /
        # empty so save/load fall back to single-file behaviour.
        self.folder_path: str | None = None
        self.pages: list[dict] = []
        self.active_page_id: str | None = None
        # Project-level + per-widget-type font defaults. Keys:
        # "_all" (every text widget) and widget type_name strings
        # ("CTkButton", ...). Cascade order is per-widget override →
        # per-type → "_all" → Tk default; resolved by
        # ``app.core.fonts.resolve_effective_family``. Persisted as a
        # top-level "font_defaults" object in the .ctkproj.
        self.font_defaults: dict[str, str] = {}
        # System fonts the user has explicitly added to the project's
        # font palette. The font picker only lists these + the
        # imported ``assets/fonts/`` files — opening every OS font is
        # both slow and overwhelms the user with hundreds of rows.
        # Adding goes through the secondary "+ Add system font"
        # dialog. Persisted as ``system_fonts`` in the .ctkproj.
        self.system_fonts: list[str] = []
        self.documents: list[Document] = [Document(name=self.name)]
        self.active_document_id: str = self.documents[0].id
        # Widget auto-name counters moved to Document.name_counters —
        # each doc (including every Dialog) now has its own count
        # sequence, and clearing / loading a project naturally resets
        # them because the counters live on the new Document instances.
        # In-memory clipboard for Ctrl+C / Ctrl+V. Each entry is a
        # full WidgetNode.to_dict() snapshot of a copied subtree.
        # Not persisted — lost when the app quits.
        self.clipboard: list[dict] = []
        # Document the clipboard contents originated from. Tracked
        # so cross-doc paste can detect that the clipboard's local
        # var tokens reference a different doc's locals and ask the
        # user how to handle them. ``None`` until the first copy.
        self._clipboard_source_doc_id: str | None = None
        # Widget-id indexes — maintained on add / remove / reparent so
        # ``get_widget`` and ``find_document_for_widget`` stay O(1)
        # instead of walking every doc's tree on every call. Group
        # drag was spending most of its per-motion budget on these
        # linear scans before the index existed.
        self._id_index: dict[str, WidgetNode] = {}
        self._doc_index: dict[str, Document] = {}
        self._window_proxy = _WindowProxy(self)
        # Phase 1 (visual scripting): project-level shared variables.
        # ``variables`` is the persisted list of declarations; ``_tk_vars``
        # is the lazy runtime cache of ``tk.Variable`` instances (keyed
        # by VariableEntry.id). Widgets bind via a ``var:<uuid>`` token
        # in their property slot; the runtime resolves the token through
        # ``get_tk_var`` and feeds the live ``tk.Variable`` to the widget
        # constructor (``textvariable=`` / ``variable=``).
        self.variables: list[VariableEntry] = []
        self._tk_vars: dict[str, tk.Variable] = {}
        # v1.10.8 Object References — global scope holds typed
        # ``ref[Window]`` / ``ref[Dialog]`` slots whose target lives in
        # ``Project.documents``. Inner-widget refs live on each
        # ``Document.local_object_references`` instead. Matches the
        # variables system's global / local split.
        self.object_references: list[ObjectReferenceEntry] = []
        # Undo / redo history. UI code pushes Command objects after
        # applying mutations; history replays them backward / forward.
        self.history = History(self)

    # ------------------------------------------------------------------
    # Document accessors — migration layer so legacy code paths that
    # read project.root_widgets / document_width / document_height /
    # window_properties keep working against the currently active
    # document. Phase 5.5 rewires rendering / drops / selection to
    # address specific documents by id; until then, everything
    # implicitly targets the active one.
    # ------------------------------------------------------------------
    @property
    def active_document(self) -> Document:
        for doc in self.documents:
            if doc.id == self.active_document_id:
                return doc
        # Defensive fallback: drift in active_document_id shouldn't
        # crash the app. Pick the first document and realign.
        if self.documents:
            self.active_document_id = self.documents[0].id
            return self.documents[0]
        # Nothing at all — create one on the fly so the rest of the
        # invariants ("there's always a document") hold.
        doc = Document()
        self.documents.append(doc)
        self.active_document_id = doc.id
        return doc

    def get_document(self, document_id: str) -> Document | None:
        for doc in self.documents:
            if doc.id == document_id:
                return doc
        return None

    def get_accent_color(self, document_id: str | None = None) -> str:
        """Return a document's theme/accent colour.

        Priority: user-picked ``doc.color`` (Window Settings) →
        hue derived from the doc's index in ``self.documents`` via
        the golden-ratio conjugate. Index-based stepping guarantees
        every doc in a project gets a visibly distinct hue — UUID
        hashing (the previous approach) could land two docs on
        perceptually-close hues (same "green-ish"), which defeats the
        purpose of the colour code.
        """
        import colorsys

        from app.core.colors import DOCUMENT_PALETTE

        doc = (
            self.get_document(document_id)
            if document_id else self.active_document
        )
        if doc is None:
            return DOCUMENT_PALETTE[0]
        if doc.color:
            return doc.color
        try:
            idx = self.documents.index(doc)
        except ValueError:
            idx = 0
        hue = (idx * 0.6180339887498949) % 1.0
        # Fixed S/L tuned for the dark builder theme: saturated
        # enough to be vivid, light enough to read on a #2d2d30 bar.
        r, g, b = colorsys.hls_to_rgb(hue, 0.65, 0.55)
        return "#{:02x}{:02x}{:02x}".format(
            int(r * 255), int(g * 255), int(b * 255),
        )

    def set_active_document(self, document_id: str) -> None:
        if document_id == self.active_document_id:
            return
        if self.get_document(document_id) is None:
            return
        self.active_document_id = document_id
        self.event_bus.publish("active_document_changed", document_id)

    def set_document_collapsed(
        self, document_id: str, collapsed: bool,
    ) -> None:
        """Toggle a document's collapsed state. Collapsed docs are
        hidden from the canvas (no rect / chrome / widget render) and
        surface as a tab in the canvas bottom-left strip — see
        ``render.py`` and ``chrome.py``.

        Activeness rules:
        - Collapsing the currently-active doc demotes it; the next
          expanded doc (in document order) is promoted. If every doc
          ends up collapsed, ``active_document_id`` keeps pointing at
          the requested doc — the canvas will simply show only tabs.
        - Expanding a collapsed doc activates it (matches the mental
          model of "I'm bringing back this window to work on it").
        """
        doc = self.get_document(document_id)
        if doc is None:
            return
        target = bool(collapsed)
        if doc.collapsed == target:
            return
        if target:
            # Clear selection if it points into the doc that's about
            # to lose its widgets — otherwise the selection chrome
            # would draw against a destroyed canvas item.
            sel = self.selected_id
            if sel is not None and sel != "__window__":
                sel_doc = self.find_document_for_widget(sel)
                if sel_doc is doc:
                    self.select_widget(None)
        doc.collapsed = target
        if target:
            if self.active_document_id == document_id:
                fallback = next(
                    (d.id for d in self.documents
                     if not d.collapsed and d.id != document_id),
                    None,
                )
                if fallback is not None:
                    self.active_document_id = fallback
                    self.event_bus.publish(
                        "active_document_changed", fallback,
                    )
        else:
            # Smart restore — if the saved position now collides with
            # another visible doc (user moved something into the gap
            # while this one was minimised), shift the restored doc to
            # the right of all visible docs. Same +120 gap as Add
            # Dialog so the spacing reads consistent.
            self._shift_if_position_occluded(doc)
            if self.active_document_id != document_id:
                self.active_document_id = document_id
                self.event_bus.publish(
                    "active_document_changed", document_id,
                )
        self.event_bus.publish(
            "document_collapsed_changed", document_id, target,
        )

    def set_document_ghost(
        self, document_id: str, ghost: bool,
    ) -> None:
        """Toggle a document's ghosted state. Ghosted docs lose their
        live widgets and are replaced on-canvas by a desaturated PIL
        screenshot (see ``ghost_manager.py``).

        Activeness rules mirror ``set_document_collapsed``: ghosting
        the active doc demotes it, expanding promotes the target.
        """
        doc = self.get_document(document_id)
        if doc is None:
            return
        target = bool(ghost)
        if doc.ghosted == target:
            return
        if target:
            sel = self.selected_id
            if sel is not None and sel != "__window__":
                sel_doc = self.find_document_for_widget(sel)
                if sel_doc is doc:
                    self.select_widget(None)
        doc.ghosted = target
        if target:
            if self.active_document_id == document_id:
                fallback = next(
                    (d.id for d in self.documents
                     if not d.ghosted and not d.collapsed
                     and d.id != document_id),
                    None,
                )
                if fallback is not None:
                    self.active_document_id = fallback
                    self.event_bus.publish(
                        "active_document_changed", fallback,
                    )
        else:
            if self.active_document_id != document_id:
                self.active_document_id = document_id
                self.event_bus.publish(
                    "active_document_changed", document_id,
                )
        self.event_bus.publish(
            "document_ghost_changed", document_id, target,
        )

    def _shift_if_position_occluded(self, doc) -> None:
        """If ``doc``'s saved canvas rectangle overlaps any other
        non-collapsed doc, move it to the right of all visible docs.

        Called from the expand path of ``set_document_collapsed`` so
        a restored window never lands underneath one the user moved
        into its old slot. The shift is permanent — next save / next
        collapse-restore cycle remembers the new position.
        """
        others = [
            d for d in self.documents
            if d is not doc and not d.collapsed
        ]
        if not others:
            return
        my_left = doc.canvas_x
        my_top = doc.canvas_y
        my_right = my_left + doc.width
        my_bottom = my_top + doc.height
        for other in others:
            ol = other.canvas_x
            ot = other.canvas_y
            orr = ol + other.width
            ob = ot + other.height
            if (
                my_left < orr and my_right > ol
                and my_top < ob and my_bottom > ot
            ):
                # Overlap — shift to the right of the rightmost other,
                # +120 gap (matches MainWindow._add_document).
                max_right = max(o.canvas_x + o.width for o in others)
                doc.canvas_x = max_right + 120
                doc.canvas_y = 0
                return

    def bring_document_to_front(self, document_id: str) -> None:
        """Make the document the topmost visible one. The active=top
        render sort (see Workspace.iter_render_order) already draws
        the active document last, so activating is enough — no list
        reorder required."""
        if self.active_document_id == document_id:
            return
        if self.get_document(document_id) is None:
            return
        self.active_document_id = document_id
        self.event_bus.publish("active_document_changed", document_id)

    def send_document_to_back(self, document_id: str) -> None:
        """Push the document behind every other.

        Two paths:
        1. Doc is already at index 0 but currently ACTIVE (so render
           order puts it on top) → deactivate, promote the next
           topmost to active. List order unchanged.
        2. Otherwise → move to index 0 in ``self.documents`` so the
           render pass draws it first. If it was the active one,
           promote the next topmost so the user isn't stuck editing
           an invisible form.
        """
        doc = self.get_document(document_id)
        if doc is None:
            return
        if len(self.documents) < 2:
            return
        idx = self.documents.index(doc)
        is_active = self.active_document_id == document_id
        if idx == 0 and not is_active:
            return  # already at back, nothing to do
        if idx > 0:
            self.documents.pop(idx)
            self.documents.insert(0, doc)
        if is_active:
            # Promote the next topmost (now last in docs list) to
            # active so the form at render-top also owns selection.
            new_active = self.documents[-1].id
            self.active_document_id = new_active
            self.event_bus.publish("active_document_changed", new_active)
        self.event_bus.publish("documents_reordered")

    @property
    def root_widgets(self) -> list[WidgetNode]:
        return self.active_document.root_widgets

    @root_widgets.setter
    def root_widgets(self, value: list[WidgetNode]) -> None:
        self.active_document.root_widgets = list(value)

    @property
    def document_width(self) -> int:
        return self.active_document.width

    @document_width.setter
    def document_width(self, value: int) -> None:
        self.active_document.width = int(value)

    @property
    def document_height(self) -> int:
        return self.active_document.height

    @document_height.setter
    def document_height(self, value: int) -> None:
        self.active_document.height = int(value)

    @property
    def window_properties(self) -> dict:
        return self.active_document.window_properties

    @window_properties.setter
    def window_properties(self, value: dict) -> None:
        self.active_document.window_properties = dict(value)

    # ------------------------------------------------------------------
    # Document
    # ------------------------------------------------------------------
    def resize_document(self, width: int, height: int) -> None:
        width = max(100, int(width))
        height = max(100, int(height))
        if width == self.document_width and height == self.document_height:
            return
        self.document_width = width
        self.document_height = height
        self.event_bus.publish("document_resized", width, height)

    # ------------------------------------------------------------------
    # Tree traversal — walks every document so lookups + selection
    # work across the entire multi-document project, not just the
    # active one.
    # ------------------------------------------------------------------
    def iter_all_widgets(self) -> Iterator[WidgetNode]:
        """Yield every widget in every document, depth-first top-down."""
        for doc in self.documents:
            yield from _walk_tree(doc.root_widgets)

    def find_document_for_widget(
        self, widget_id: str,
    ) -> Document | None:
        """Return the Document whose tree contains ``widget_id``.
        ``_doc_index`` gives O(1) lookups for indexed widgets; the
        fallback linear scan handles the (rare) case where the index
        got out of sync — better to pay O(N) once than crash.
        """
        hit = self._doc_index.get(widget_id)
        if hit is not None:
            return hit
        for doc in self.documents:
            for node in _walk_tree(doc.root_widgets):
                if node.id == widget_id:
                    # Heal: re-populate the index so the next lookup
                    # is O(1). Happens when a consumer creates widgets
                    # outside the add_widget path.
                    self._doc_index[widget_id] = doc
                    return doc
        return None

    def get_widget(self, widget_id: str):
        if widget_id == WINDOW_ID:
            return self._window_proxy
        hit = self._id_index.get(widget_id)
        if hit is not None:
            return hit
        for node in self.iter_all_widgets():
            if node.id == widget_id:
                self._id_index[widget_id] = node
                return node
        return None

    def _sibling_list(self, node: WidgetNode) -> list[WidgetNode]:
        """Return the list that contains `node` (its parent's children
        or the document's root list when top-level). Walks every
        document so nodes from non-active documents still resolve
        correctly."""
        if node.parent is not None:
            return node.parent.children
        doc = self.find_document_for_widget(node.id)
        if doc is not None:
            return doc.root_widgets
        # Fallback: active document's roots, matching pre-refactor
        # behaviour for orphan / in-flight nodes.
        return self.active_document.root_widgets

    # ------------------------------------------------------------------
    # Naming
    # ------------------------------------------------------------------
    def _generate_unique_name(
        self, widget_type: str, document=None, base: str | None = None,
    ) -> str:
        """Identifier-safe monotonic name: 'CTkButton' → 'button_1'
        → 'button_2' → ...

        Uses the slug that ``_resolve_var_names`` applies — strip the
        ``CTk`` prefix, lowercase — so the Properties-panel ``Name``
        is already a valid Python identifier and the export-time
        fallback dialog never fires for newly dropped widgets.
        ``base`` lets palette layouts override the slug
        ("vertical_layout", "horizontal_layout", "grid_layout") so
        the Object Tree still distinguishes them despite all three
        being CTkFrame.

        Counter bucket is the resolved ``base`` (not ``widget_type``)
        so a layout-distinct base increments independently from the
        generic ``frame`` bucket.

        Counter is **per document** (stored on ``Document.name_counters``)
        so each dialog restarts from zero and a freshly opened project
        doesn't inherit counts from the previous editing session.
        """
        if not base:
            base = widget_type.replace("CTk", "").lower() or "widget"

        target_doc = document or self.active_document
        counters = target_doc.name_counters
        count = counters.get(base, 0) + 1
        counters[base] = count

        return f"{base}_{count}"

    def rename_widget(self, widget_id: str, new_name: str) -> None:
        # The virtual Window node renames the *active document* —
        # i.e. the form's window title, which is independent of the
        # project filename (only changed via New / Save As).
        if widget_id == WINDOW_ID:
            doc = self.active_document
            if doc.name == new_name:
                return
            old_name = doc.name
            doc.name = new_name
            self.event_bus.publish("widget_renamed", widget_id, new_name)
            # ``document_renamed`` carries old_name so subscribers can
            # locate the previous behavior-file path on disk before
            # the rename. Phase 2 Step 3 wires this to the per-window
            # ``.py`` rename + class-name rewrite.
            self.event_bus.publish(
                "document_renamed", doc.id, old_name, new_name,
            )
            return
        node = self.get_widget(widget_id)
        if not isinstance(node, WidgetNode):
            return
        if node.name == new_name:
            return
        node.name = new_name
        self.event_bus.publish("widget_renamed", widget_id, new_name)

    # ------------------------------------------------------------------
    # Add / remove / reparent
    # ------------------------------------------------------------------
    def _resolve_target_document(self, document_id: str | None):
        """Return the Document that a top-level op should target.

        ``document_id`` wins when given and it matches an existing doc
        (used by undo/redo + paste to restore into the original doc);
        otherwise fall back to the currently active document so callers
        without a specific doc in mind get today's behaviour.
        """
        if document_id:
            doc = self.get_document(document_id)
            if doc is not None:
                return doc
        return self.active_document

    def _index_subtree(self, node: WidgetNode, doc: "Document") -> None:
        """Index ``node`` + every descendant under ``doc``.

        Called on add / reparent so ``get_widget`` and
        ``find_document_for_widget`` stay O(1). Fallback linear scans
        still work when a widget somehow isn't in the index.
        """
        for desc in _walk_tree([node]):
            self._id_index[desc.id] = desc
            self._doc_index[desc.id] = doc

    def _unindex_subtree(self, node: WidgetNode) -> None:
        for desc in _walk_tree([node]):
            self._id_index.pop(desc.id, None)
            self._doc_index.pop(desc.id, None)

    def add_widget(
        self, node: WidgetNode, parent_id: str | None = None,
        document_id: str | None = None, name_base: str | None = None,
    ) -> None:
        if parent_id is None:
            target_doc = self._resolve_target_document(document_id)
            node.parent = None
            if not node.name:
                node.name = self._generate_unique_name(
                    node.widget_type, document=target_doc, base=name_base,
                )
            target_doc.root_widgets.append(node)
            owning_doc = target_doc
        else:
            parent = self.get_widget(parent_id)
            if not isinstance(parent, WidgetNode):
                # unknown parent id, or WINDOW_ID (proxy can't own
                # children): fall back to top-level to avoid silently
                # dropping the node.
                node.parent = None
                self.root_widgets.append(node)
                owning_doc = self.active_document
            else:
                node.parent = parent
                parent.children.append(node)
                owning_doc = self._doc_index.get(parent_id) or (
                    self.find_document_for_widget(parent_id)
                    or self.active_document
                )
            if not node.name:
                node.name = self._generate_unique_name(
                    node.widget_type, document=owning_doc, base=name_base,
                )
        self._index_subtree(node, owning_doc)
        self.event_bus.publish("widget_added", node)

    def remove_widget(self, widget_id: str) -> None:
        node = self.get_widget(widget_id)
        if not isinstance(node, WidgetNode):
            return
        # Remove descendants first (depth-first) so listeners see
        # children disappear before their parent.
        for child in list(node.children):
            self.remove_widget(child.id)
        siblings = self._sibling_list(node)
        if node in siblings:
            siblings.remove(node)
        parent_id = node.parent.id if node.parent is not None else None
        node.parent = None
        self._id_index.pop(widget_id, None)
        self._doc_index.pop(widget_id, None)
        if self.selected_id == widget_id:
            self.select_widget(None)
        self.event_bus.publish("widget_removed", widget_id, parent_id)

    def reparent(
        self,
        widget_id: str,
        new_parent_id: str | None,
        index: int | None = None,
        document_id: str | None = None,
    ) -> None:
        """Move a node between parents and/or to a new sibling position.

        - ``new_parent_id=None`` → top-level
        - ``index=None`` → append to the end of the target sibling list
        - ``index=N`` → insert at position N (clamped)
        - ``document_id`` → target doc for top-level moves; without it
          top-level falls back to the currently active document, which
          is wrong for cross-doc undo/redo replay.

        Publishes ``widget_reparented`` when the parent actually changes,
        or ``widget_z_changed(direction="reorder")`` when only the
        sibling order changed.
        """
        node = self.get_widget(widget_id)
        if not isinstance(node, WidgetNode):
            return
        # WINDOW_ID as new_parent collapses to top-level: the proxy
        # can't own children, so dropping "into" it is identical to a
        # top-level drop in the active doc.
        resolved_parent = (
            self.get_widget(new_parent_id) if new_parent_id else None
        )
        new_parent = (
            resolved_parent if isinstance(resolved_parent, WidgetNode)
            else None
        )
        # Refuse to make a node a descendant of itself.
        if new_parent is not None and self._is_descendant(new_parent, node):
            return

        old_parent = node.parent
        old_parent_id = old_parent.id if old_parent is not None else None
        parent_changed = old_parent_id != new_parent_id
        old_doc = self.find_document_for_widget(widget_id)
        # Resolve target doc from whichever info is available:
        #   1) when ``new_parent`` is set, the parent's own doc is the
        #      most reliable source of truth (drop into a Frame in
        #      another window).
        #   2) explicit ``document_id`` arg (used by undo / redo / paste
        #      replay against a specific doc).
        #   3) fall back to the active document — last resort, may be
        #      stale during a drag where the focus hasn't switched yet.
        # The earlier "only when ``new_parent is None``" gate missed
        # cross-doc moves that landed inside a Frame and missed top-
        # level drops where the active doc was still the source.
        if new_parent is not None:
            target_doc = self.find_document_for_widget(new_parent.id)
        else:
            target_doc = self._resolve_target_document(document_id)
        doc_changed = (
            old_doc is not None
            and target_doc is not None
            and old_doc.id != target_doc.id
        )

        old_siblings = self._sibling_list(node)
        try:
            old_index = old_siblings.index(node)
        except ValueError:
            old_index = None

        # Early-out: same parent, same doc, same index.
        if (not parent_changed and not doc_changed
                and (index is None or index == old_index)):
            return

        if old_index is not None:
            old_siblings.pop(old_index)

        if new_parent is not None:
            target_siblings = new_parent.children
        else:
            # ``target_doc`` is None only when the project has no
            # documents at all — defensively fall back to whichever
            # doc still holds the node so we don't crash.
            siblings_owner = target_doc or old_doc
            target_siblings = (
                siblings_owner.root_widgets
                if siblings_owner is not None else []
            )

        # If staying in the same sibling list and the original slot
        # was before the target slot, removing the node shifted
        # everything after it left by one — compensate.
        if (not parent_changed
                and index is not None
                and old_index is not None
                and old_index < index):
            index -= 1

        node.parent = new_parent
        if index is None:
            target_siblings.append(node)
        else:
            clamped = max(0, min(index, len(target_siblings)))
            target_siblings.insert(clamped, node)

        # Re-index the moved subtree under its new doc. Parent-only
        # reorder within the same doc doesn't change ``_doc_index``,
        # but doc-crossing moves would otherwise leave stale entries.
        # Local-variable migration is the UI's responsibility now —
        # the cross-doc reparent dialog asks the user for source and
        # target policies and then calls
        # ``migrate_local_var_bindings`` directly. Doing it here would
        # bypass the dialog and pin every drag to the "Keep + Duplicate"
        # default. The load-time repair path explicitly opts in.
        if doc_changed and target_doc is not None:
            self._index_subtree(node, target_doc)

        if parent_changed or doc_changed:
            self.event_bus.publish(
                "widget_reparented", widget_id,
                old_parent_id, new_parent_id,
            )
        else:
            self.event_bus.publish(
                "widget_z_changed", widget_id, "reorder",
            )

    def _is_descendant(
        self, candidate: WidgetNode, ancestor: WidgetNode,
    ) -> bool:
        node: WidgetNode | None = candidate
        while node is not None:
            if node is ancestor:
                return True
            node = node.parent
        return False

    def clear(self) -> None:
        # Remove every widget across every document — listeners
        # (workspace, object tree, properties panel) observe these
        # one by one and tear down their views. Afterward the
        # document list is reset to a single fresh Main Window so
        # the project always has exactly one document.
        for doc in list(self.documents):
            for node in list(doc.root_widgets):
                self.remove_widget(node.id)
        self._id_index.clear()
        self._doc_index.clear()
        # Default doc name = project name so a clear() right after
        # load keeps the doc name in sync with whatever the user
        # picked for the project title.
        self.documents = [Document(name=self.name or "Untitled")]
        self.active_document_id = self.documents[0].id
        self.history.clear()
        # Reset font cascade + system_fonts list — without this, the
        # next New Project inherits the previous project's defaults
        # and ImageFont-imported families, so widgets that reference
        # nothing locally still get rendered with stale fonts.
        # ``_set_current_path`` calls ``set_active_project_defaults``
        # right after, which propagates this empty state to the
        # module-level cache.
        self.font_defaults = {}
        self.system_fonts = []
        # Multi-page metadata (folder_path / pages / active_page_id)
        # is reset here too — the loader / New Project flow re-seeds
        # it right after ``clear()``.
        self.folder_path = None
        self.pages = []
        self.active_page_id = None
        # Phase 1: drop variable declarations + cached tk vars so a
        # New Project / Open doesn't inherit the previous project's
        # state.
        self.variables = []
        self.reset_tk_vars()
        self.event_bus.publish(
            "active_document_changed", self.active_document_id,
        )

    # ------------------------------------------------------------------
    # Selection + properties
    # ------------------------------------------------------------------
    def select_widget(self, widget_id: str | None) -> None:
        """Single-selection entry point. Replaces `selected_ids` with
        {widget_id} or an empty set."""
        new_ids: set[str] = {widget_id} if widget_id else set()
        if widget_id == self.selected_id and new_ids == self.selected_ids:
            return
        self.selected_id = widget_id
        self.selected_ids = new_ids
        self.event_bus.publish("selection_changed", widget_id)

    def set_multi_selection(
        self, ids: set[str], primary: str | None = None,
    ) -> None:
        """Replace selection with a set. Emits `selection_changed`
        with the primary id when there's 0 or 1 selected, and with
        `None` when there are 2+ — this naturally clears the
        workspace handles + properties panel while the tree keeps
        its own multi-row highlight."""
        new_ids = {i for i in ids if i is not None}
        # Group invariant — within one group, only single selection
        # is allowed; the only way more than one member coexists in
        # the selection is when EVERY member of that group is
        # present (whole-group selection via tree row / right-click).
        # Mixed selection (some members + non-members) is also
        # rejected to keep the rule simple.
        new_ids = self._enforce_group_invariant(new_ids, primary)
        if primary is not None and primary not in new_ids:
            primary = None
        if primary is None and new_ids:
            primary = next(iter(new_ids))
        if new_ids == self.selected_ids and primary == self.selected_id:
            return
        self.selected_ids = new_ids
        self.selected_id = primary
        display = primary if len(new_ids) <= 1 else None
        self.event_bus.publish("selection_changed", display)

    def _enforce_group_invariant(
        self, ids: set, primary: str | None,
    ) -> set:
        """Each group in the selection is either fully present or
        fully absent — never partial. Non-group widgets pass through
        untouched, and multiple full groups can coexist. When a group
        is partially present the function reduces it to a single
        keeper (preferring ``primary``) so the selection stays
        consistent. Pure, no side effects.
        """
        if not ids:
            return ids
        group_buckets: dict = {}
        non_group: set = set()
        for wid in ids:
            node = self._id_index.get(wid) or self.get_widget(wid)
            gid = getattr(node, "group_id", None) if node else None
            if gid:
                group_buckets.setdefault(gid, set()).add(wid)
            else:
                non_group.add(wid)
        if not group_buckets:
            return ids
        kept: set = set(non_group)
        for gid, present in group_buckets.items():
            full = {m.id for m in self.iter_group_members(gid)}
            if present == full:
                kept |= present
                continue
            # Partial group → collapse to one keeper (primary if it's
            # inside this group, else any member).
            if primary in present:
                kept.add(primary)
            else:
                kept.add(next(iter(present)))
        return kept

    def update_property(
        self, widget_id: str, prop_name: str, value,
    ) -> None:
        if widget_id == WINDOW_ID:
            self._set_window_property(prop_name, value)
            return
        node = self.get_widget(widget_id)
        if node is None:
            return
        node.properties[prop_name] = value
        self.event_bus.publish(
            "property_changed", widget_id, prop_name, value,
        )

    # ------------------------------------------------------------------
    # Window (virtual node) setters
    # ------------------------------------------------------------------
    def _set_window_property(self, prop_name: str, value) -> None:
        """Route an update on the virtual Window node to the right
        field. Width/height dispatch to ``resize_document`` so the
        workspace canvas and everything else stays in sync; other
        keys land in ``window_properties`` and publish the normal
        ``property_changed`` event so the panel + history pick them
        up."""
        if prop_name == "width":
            try:
                w = int(value)
            except (TypeError, ValueError):
                return
            self.resize_document(w, self.document_height)
            self.event_bus.publish(
                "property_changed", WINDOW_ID, prop_name, w,
            )
            return
        if prop_name == "height":
            try:
                h = int(value)
            except (TypeError, ValueError):
                return
            self.resize_document(self.document_width, h)
            self.event_bus.publish(
                "property_changed", WINDOW_ID, prop_name, h,
            )
            return
        if prop_name == "accent_color":
            doc = self.active_document
            if doc is not None:
                # Empty / falsy value resets to the auto palette pick;
                # any hex string wins as a user override.
                doc.color = value if value else None
                self.event_bus.publish(
                    "property_changed", WINDOW_ID, prop_name, value,
                )
            return
        self.window_properties[prop_name] = value
        self.event_bus.publish(
            "property_changed", WINDOW_ID, prop_name, value,
        )

    # ==================================================================
    # Variables (Phase 1 visual scripting — shared state)
    #
    # Two scopes:
    #   * ``"global"`` lives on ``self.variables`` (project-wide)
    #   * ``"local"``  lives on ``Document.local_variables`` (per-doc)
    #
    # The token (``var:<uuid>``) does not encode scope — UUIDs are
    # globally unique, and the registry resolves scope on lookup.
    # Visibility rule: a widget in document D may bind to globals + the
    # locals of D. Other docs' locals are blocked at the binding-menu
    # level and at code-export time.
    # ==================================================================
    def _get_var_list(
        self, scope: str, document_id: str | None,
    ) -> list[VariableEntry]:
        """Return the list backing the given scope. Locals require a
        ``document_id``; passing ``None`` falls back to the active
        document. Raises ``ValueError`` for an unknown scope so caller
        bugs surface immediately instead of silently writing to the
        wrong list.
        """
        if scope == "global":
            return self.variables
        if scope == "local":
            doc = (
                self.get_document(document_id)
                if document_id else self.active_document
            )
            if doc is None:
                raise ValueError(
                    "local variable requires a valid document",
                )
            return doc.local_variables
        raise ValueError(f"unknown variable scope: {scope!r}")

    def find_document_for_variable(
        self, var_id: str,
    ) -> Document | None:
        """Document that owns the given local variable, or ``None`` for
        globals / unknown ids. Used by undo, code-export, and the
        Variables window to find the right list when only the UUID is
        in hand.
        """
        for doc in self.documents:
            for v in doc.local_variables:
                if v.id == var_id:
                    return doc
        return None

    def get_variable_scope(self, var_id: str) -> str | None:
        """Return ``"global"`` / ``"local"`` for a known UUID, ``None``
        when no entry exists with that id.
        """
        for v in self.variables:
            if v.id == var_id:
                return "global"
        if self.find_document_for_variable(var_id) is not None:
            return "local"
        return None

    def iter_variables(
        self,
        scope: str | None = None,
        document_id: str | None = None,
    ) -> Iterator[VariableEntry]:
        """Iterate the variables visible from the given context.

        ``scope=None`` (default) yields globals first, then the locals
        of ``document_id`` (or the active doc if not given). This is
        the visibility rule used by binding menus.

        ``scope="global"`` yields only globals; ``scope="local"``
        yields only the document's locals.
        """
        if scope in (None, "global"):
            yield from self.variables
        if scope in (None, "local"):
            doc = (
                self.get_document(document_id)
                if document_id else self.active_document
            )
            if doc is not None:
                yield from doc.local_variables

    def add_variable(
        self, name: str, var_type: str = "str", default: str = "",
        var_id: str | None = None,
        scope: str = "global",
        document_id: str | None = None,
    ) -> VariableEntry:
        """Append a new variable to the project. Names are sanitised
        toward Python identifiers; types outside the supported set
        fall back to ``"str"``. Pass ``var_id`` to restore an existing
        UUID (used by undo / paste). ``scope="local"`` stores the
        entry on the given document's ``local_variables`` instead of
        the project-wide list.
        """
        clean_type = var_type if var_type in VAR_TYPES else "str"
        target = self._get_var_list(scope, document_id)
        clean_name = self._dedupe_var_name(
            sanitize_var_name(name or "var"),
            scope=scope, document_id=document_id,
        )
        clean_default = coerce_default_for_type(default, clean_type)
        entry = VariableEntry(
            name=clean_name, type=clean_type, default=clean_default,
            scope="local" if scope == "local" else "global",
        )
        if var_id:
            entry.id = var_id
        target.append(entry)
        # Lazy: ``tk.Variable`` is created on first ``get_tk_var`` call.
        self.event_bus.publish("variable_added", entry)
        return entry

    def remove_variable(self, var_id: str) -> VariableEntry | None:
        """Remove a variable + tear down its tk var. Cascade-unbinds
        every widget property that references it so nothing dangles
        after delete. Works for both scopes — the registry resolves
        which list to mutate. Returns the removed entry (or ``None``
        when the id wasn't known).
        """
        entry = self.get_variable(var_id)
        if entry is None:
            return None
        for node, pname in list(self.iter_bindings_for(var_id)):
            node.properties.pop(pname, None)
            self.event_bus.publish(
                "property_changed", node.id, pname, None,
            )
        if entry.scope == "local":
            owner = self.find_document_for_variable(var_id)
            if owner is not None:
                owner.local_variables = [
                    v for v in owner.local_variables if v.id != var_id
                ]
        else:
            self.variables = [
                v for v in self.variables if v.id != var_id
            ]
        self._tk_vars.pop(var_id, None)
        self.event_bus.publish("variable_removed", var_id)
        return entry

    def rename_variable(self, var_id: str, new_name: str) -> None:
        entry = self.get_variable(var_id)
        if entry is None:
            return
        owner_doc_id = None
        if entry.scope == "local":
            owner = self.find_document_for_variable(var_id)
            owner_doc_id = owner.id if owner else None
        clean = self._dedupe_var_name(
            sanitize_var_name(new_name or "var"),
            scope=entry.scope,
            document_id=owner_doc_id,
            exclude_id=var_id,
        )
        if clean == entry.name:
            return
        entry.name = clean
        self.event_bus.publish("variable_renamed", var_id, clean)

    def change_variable_type(self, var_id: str, new_type: str) -> None:
        """Change a variable's runtime type. Coerces the existing
        default into the new type's safe value and drops the cached
        ``tk.Variable`` so every bound widget rebuilds against the
        new kind on its next reconfigure.
        """
        entry = self.get_variable(var_id)
        if entry is None:
            return
        clean_type = new_type if new_type in VAR_TYPES else "str"
        if clean_type == entry.type:
            return
        entry.type = clean_type
        entry.default = coerce_default_for_type(
            entry.default, clean_type,
        )
        self._tk_vars.pop(var_id, None)
        self.event_bus.publish(
            "variable_type_changed", var_id, clean_type,
        )

    def change_variable_default(
        self, var_id: str, new_default: str,
    ) -> None:
        entry = self.get_variable(var_id)
        if entry is None:
            return
        clean = coerce_default_for_type(new_default, entry.type)
        if clean == entry.default:
            return
        entry.default = clean
        # Push the new default into the live tk var so every bound
        # widget updates instantly.
        tk_var = self._tk_vars.get(var_id)
        if tk_var is not None:
            try:
                tk_var.set(clean)
            except Exception:
                pass
        self.event_bus.publish(
            "variable_default_changed", var_id, clean,
        )

    def get_variable(self, var_id: str) -> VariableEntry | None:
        for v in self.variables:
            if v.id == var_id:
                return v
        for doc in self.documents:
            for v in doc.local_variables:
                if v.id == var_id:
                    return v
        return None

    def get_variable_by_name(
        self, name: str, document_id: str | None = None,
    ) -> VariableEntry | None:
        """Visibility-aware name lookup. Globals win over a same-named
        local in the active doc — exporter code uses this to resolve
        token-less name references where a literal collision is
        possible. Pass ``document_id`` explicitly to query a specific
        document's locals; otherwise the active doc's locals are used.
        """
        for v in self.variables:
            if v.name == name:
                return v
        doc = (
            self.get_document(document_id)
            if document_id else self.active_document
        )
        if doc is not None:
            for v in doc.local_variables:
                if v.name == name:
                    return v
        return None

    def get_tk_var(self, var_id: str):
        """Return the live ``tk.Variable`` for ``var_id``, building it
        on first request. Returns ``None`` when the id isn't known —
        callers degrade by ignoring the binding (the property slot
        falls back to its descriptor default). Locals and globals
        share one cache because UUIDs are unique across both pools.
        """
        tk_var = self._tk_vars.get(var_id)
        if tk_var is not None:
            return tk_var
        entry = self.get_variable(var_id)
        if entry is None:
            return None
        tk_var = make_tk_var(entry.type, entry.default)
        self._tk_vars[var_id] = tk_var
        return tk_var

    def iter_bindings_for(
        self, var_id: str,
    ) -> Iterator[tuple[WidgetNode, str]]:
        """Yield ``(node, prop_name)`` for every property holding a
        ``var:<var_id>`` token. Used by Variables panel ("used by N
        widgets") and by ``remove_variable`` for cascade-unbind.
        """
        for node in self.iter_all_widgets():
            for pname, pvalue in list(node.properties.items()):
                if parse_var_token(pvalue) == var_id:
                    yield node, pname

    def collect_cross_doc_local_vars(
        self, root_nodes, target_doc,
    ) -> tuple[list, int]:
        """Survey ``root_nodes`` for local-variable bindings that
        cross into ``target_doc``.

        Returns ``(var_entries, external_usage)``:
            ``var_entries``    — unique local ``VariableEntry`` objects
                                 referenced by the moved subtree(s)
                                 whose owner is NOT ``target_doc``.
            ``external_usage`` — total number of widgets *outside* the
                                 moved subtree(s) that bind to those
                                 same variables. Drives the dialog's
                                 "used by N other widgets" hint.

        Globals + dangling tokens skipped. The caller uses the return
        value to decide whether the reparent dialog needs to fire.
        """
        if not root_nodes or target_doc is None:
            return [], 0
        moved_ids: set[str] = set()
        roots = list(root_nodes)
        for root in roots:
            for node in _walk_tree([root]):
                moved_ids.add(node.id)
        seen: dict[str, VariableEntry] = {}
        for root in roots:
            for node in _walk_tree([root]):
                for pvalue in node.properties.values():
                    var_id = parse_var_token(pvalue)
                    if var_id is None or var_id in seen:
                        continue
                    entry = self.get_variable(var_id)
                    if entry is None or entry.scope != "local":
                        continue
                    owner = self.find_document_for_variable(var_id)
                    if owner is None or owner is target_doc:
                        continue
                    seen[var_id] = entry
        external = 0
        for var_id in seen:
            for node, _pname in self.iter_bindings_for(var_id):
                if node.id not in moved_ids:
                    external += 1
        return list(seen.values()), external

    def migrate_local_var_bindings(
        self, root_node, target_doc,
        source_policy: str = "keep",
        target_policy: str = "duplicate",
    ) -> int:
        """Re-home local-variable bindings inside ``root_node``'s
        subtree onto ``target_doc`` according to the given policies.

        ``source_policy``:
            ``"keep"``   — variable stays in its source doc as-is
                           (default; matches load-time repair behaviour
                           and the no-dialog fast path).
            ``"delete"`` — variable + all its bindings are removed via
                           the standard ``remove_variable`` cascade.
                           Other widgets in the source that referenced
                           it lose their binding.

        ``target_policy``:
            ``"duplicate"`` — copy variable into ``target_doc``
                              (suffix dedup on name collision; same
                              name + type reuses the existing entry).
                              Tokens in the moved subtree retoken to
                              the target's UUID.
            ``"unbind"``    — drop the binding from the moved
                              subtree's properties; the descriptor's
                              default literal takes over at the next
                              read.

        Globals + dangling tokens skipped. Returns the number of
        unique source variables that triggered a write (copies under
        ``"duplicate"``, deletions under ``"delete"``). Publishes
        ``local_variables_migrated`` on a non-zero count so the
        workspace can show the status toast.
        """
        if target_doc is None or root_node is None:
            return 0
        roots = (
            list(root_node) if isinstance(root_node, (list, tuple))
            else [root_node]
        )
        # First pass: walk tokens, decide remap per source var.
        remap: dict[str, str | None] = {}  # old_id -> new_id or None (unbind)
        source_vars_to_delete: list[str] = []
        for root in roots:
            for node in _walk_tree([root]):
                for pname, pvalue in list(node.properties.items()):
                    old_id = parse_var_token(pvalue)
                    if old_id is None:
                        continue
                    if old_id in remap:
                        new_id = remap[old_id]
                        if new_id is None:
                            node.properties.pop(pname, None)
                        else:
                            node.properties[pname] = make_var_token(new_id)
                        continue
                    old_entry = self.get_variable(old_id)
                    if old_entry is None:
                        continue
                    if old_entry.scope == "global":
                        continue
                    owner = self.find_document_for_variable(old_id)
                    if owner is None or owner is target_doc:
                        continue
                    if target_policy == "duplicate":
                        # Reuse a target entry whose name + type
                        # match — keeps round-trips clean and avoids
                        # ``name_2`` / ``name_3`` accumulation.
                        existing = next(
                            (
                                v for v in target_doc.local_variables
                                if v.name == old_entry.name
                                and v.type == old_entry.type
                            ),
                            None,
                        )
                        if existing is not None:
                            new_entry_id = existing.id
                        else:
                            new_entry = self.add_variable(
                                old_entry.name, old_entry.type,
                                old_entry.default,
                                scope="local",
                                document_id=target_doc.id,
                            )
                            new_entry_id = new_entry.id
                        remap[old_id] = new_entry_id
                        node.properties[pname] = make_var_token(new_entry_id)
                    else:
                        # ``unbind`` — drop the property so the
                        # descriptor default (or literal default) takes
                        # over at next read.
                        remap[old_id] = None
                        node.properties.pop(pname, None)
                    if (
                        source_policy == "delete"
                        and old_id not in source_vars_to_delete
                    ):
                        source_vars_to_delete.append(old_id)
        # Second pass: source-side cleanup. ``remove_variable`` handles
        # cascade-unbind for any external widgets that were bound to
        # the variable.
        for var_id in source_vars_to_delete:
            self.remove_variable(var_id)
        count = len(remap)
        if count > 0:
            self.event_bus.publish("local_variables_migrated", count)
        return count

    def _dedupe_var_name(
        self, base: str,
        scope: str = "global",
        document_id: str | None = None,
        exclude_id: str | None = None,
    ) -> str:
        """Append ``_2`` / ``_3`` / ... to keep variable names unique
        within their scope. Globals dedupe against all globals;
        locals dedupe only against same-document locals. Same name
        re-used across two documents is allowed by design.
        ``exclude_id`` skips one entry so renaming-to-self is a no-op.
        """
        if scope == "local":
            doc = (
                self.get_document(document_id)
                if document_id else self.active_document
            )
            pool = doc.local_variables if doc is not None else []
        else:
            pool = self.variables
        used = {v.name for v in pool if v.id != exclude_id}
        if base not in used:
            return base
        i = 2
        while f"{base}_{i}" in used:
            i += 1
        return f"{base}_{i}"

    def reset_tk_vars(self) -> None:
        """Drop every cached ``tk.Variable``. Called by ``clear`` /
        load paths so stale tk vars from a previous project don't
        survive into the new one.
        """
        self._tk_vars.clear()

    def set_visibility(self, widget_id: str, visible: bool) -> None:
        """Toggle a node's builder-only visibility flag and notify
        listeners (workspace hides/shows, Object Tree dims the row).
        The model is unaffected beyond the boolean; save/load/export
        all continue to include the node."""
        node = self.get_widget(widget_id)
        if not isinstance(node, WidgetNode):
            return
        visible = bool(visible)
        if node.visible == visible:
            return
        node.visible = visible
        self.event_bus.publish("widget_visibility_changed", widget_id, visible)

    def set_locked(self, widget_id: str, locked: bool) -> None:
        """Toggle a node's builder-only lock flag. Locked nodes still
        render and export as usual, but the workspace refuses to
        drag / resize / nudge / delete them. Cascades through
        descendants at check-time (see workspace._effective_locked).
        """
        node = self.get_widget(widget_id)
        if not isinstance(node, WidgetNode):
            return
        locked = bool(locked)
        if node.locked == locked:
            return
        node.locked = locked
        self.event_bus.publish("widget_locked_changed", widget_id, locked)

    def set_group_id(
        self, widget_id: str, group_id: str | None,
    ) -> None:
        """Set or clear a widget's group tag. Group tags are
        builder-only metadata: clicking any member selects the whole
        group, drag moves them as one. Skipped from code export.
        """
        node = self.get_widget(widget_id)
        if not isinstance(node, WidgetNode):
            return
        if node.group_id == group_id:
            return
        node.group_id = group_id
        self.event_bus.publish(
            "widget_group_changed", widget_id, group_id,
        )

    def iter_group_members(self, group_id: str) -> list:
        """All widgets currently tagged with ``group_id`` across every
        document. Order matches ``iter_all_widgets`` (DFS top-down)."""
        if not group_id:
            return []
        return [
            n for n in self.iter_all_widgets()
            if getattr(n, "group_id", None) == group_id
        ]

    def can_group_selection(self, ids) -> bool:
        """True when ``ids`` can be tagged as a single group. Groups
        live within one parent only — cross-parent or layout-managed
        parents are rejected up front so the rest of the codebase can
        rely on every group sharing one geometry context.
        """
        from app.widgets.layout_schema import is_layout_container
        if not ids:
            return False
        nodes = [self.get_widget(wid) for wid in ids]
        nodes = [n for n in nodes if n is not None]
        if len(nodes) < 2:
            return False
        parents = {
            (n.parent.id if n.parent is not None else None) for n in nodes
        }
        if len(parents) > 1:
            return False
        parent_node = nodes[0].parent
        if parent_node is not None and is_layout_container(
            parent_node.properties,
        ):
            return False
        if any(getattr(n, "group_id", None) for n in nodes):
            return False
        return True

    # ------------------------------------------------------------------
    # Sibling operations
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Clipboard (Ctrl+C / Ctrl+V)
    # ------------------------------------------------------------------
    def copy_to_clipboard(self, ids) -> int:
        """Snapshot the given widget subtrees into `self.clipboard`.

        Iterates the tree in DFS top-down order so the clipboard
        preserves sibling z-order. Descendants whose ancestor is also
        in `ids` are skipped — copying a container already covers its
        children.

        Returns the number of top-level snapshots stored.
        """
        if not ids:
            return 0
        ids_set = set(ids)
        top_level: list[WidgetNode] = []
        for node in self.iter_all_widgets():
            if node.id not in ids_set:
                continue
            ancestor = node.parent
            is_descendant = False
            while ancestor is not None:
                if ancestor.id in ids_set:
                    is_descendant = True
                    break
                ancestor = ancestor.parent
            if not is_descendant:
                top_level.append(node)
        self.clipboard = [node.to_dict() for node in top_level]
        # Track the doc the clipboard items came from. All snapshots
        # share a single source by construction (copy operates on the
        # current selection inside one doc). Use the first node's
        # owning doc as the canonical source.
        first_owner = (
            self.find_document_for_widget(top_level[0].id)
            if top_level else None
        )
        self._clipboard_source_doc_id = (
            first_owner.id if first_owner is not None else None
        )
        return len(self.clipboard)

    def collect_clipboard_local_vars(
        self, target_doc,
    ) -> tuple[list, int]:
        """Survey the clipboard for local-variable bindings whose
        owner doc isn't ``target_doc`` — same scoping rule the
        cross-doc reparent dialog uses. Returns
        ``(var_entries, external_usage)``; empty list when no
        cross-doc local bindings exist (caller skips the dialog).
        ``external_usage`` is non-zero only when the clipboard's
        source doc still holds the original widgets bound to those
        same vars.
        """
        if not self.clipboard or target_doc is None:
            return [], 0
        seen: dict[str, VariableEntry] = {}

        def walk(node_dict: dict) -> None:
            for value in node_dict.get("properties", {}).values():
                var_id = parse_var_token(value)
                if var_id is None or var_id in seen:
                    continue
                entry = self.get_variable(var_id)
                if entry is None or entry.scope != "local":
                    continue
                owner = self.find_document_for_variable(var_id)
                if owner is None or owner is target_doc:
                    continue
                seen[var_id] = entry
            for child in node_dict.get("children") or []:
                walk(child)

        for snap in self.clipboard:
            walk(snap)
        # External usage ignores the clipboard snapshots themselves
        # (they're disk-style dicts, not live nodes) — only
        # already-rooted widgets bound to the var count.
        external = 0
        for var_id in seen:
            external += sum(
                1 for _ in self.iter_bindings_for(var_id)
            )
        return list(seen.values()), external

    def paste_from_clipboard(
        self, parent_id: str | None = None,
        base_position: tuple[int, int] | None = None,
        var_policy: tuple[str, str] | None = ("keep", "duplicate"),
    ) -> list[str]:
        """Recreate the clipboard snapshots under `parent_id` with
        fresh UUIDs + auto-generated names. Each top-level paste is
        offset by (+20, +20) so it doesn't land exactly on top of the
        original. Pasted widgets become the new selection.

        When ``base_position`` is given (logical x, y), every top-level
        clone lands at that position plus a per-item cascade offset —
        overrides the default "nudge from original coords" so canvas
        right-click paste can place the widget where the cursor is.

        ``var_policy`` controls how local-variable bindings in the
        clipboard are migrated when the paste lands in a different
        doc than the clipboard's source. ``("keep", "duplicate")`` is
        the default and matches the no-dialog fast path. ``None``
        skips migration entirely (the cross-doc reparent dialog has
        already applied the user's choice via a prior call). The
        full set of policies is documented on
        ``migrate_local_var_bindings``.

        Returns the list of new top-level widget ids.
        """
        from app.widgets.layout_schema import is_layout_container
        if not self.clipboard:
            return []
        # Block layout-in-layout nesting on paste — drag/drop already
        # blocks this at the source (WS-33), but copy-paste sneaks
        # through. If the parent is a layout container AND any clipboard
        # entry is itself a layout container, redirect the paste to
        # top-level so the rendering stays sane.
        if parent_id is not None:
            parent = self.get_widget(parent_id)
            if (
                parent is not None
                and is_layout_container(parent.properties)
                and any(
                    is_layout_container(entry.get("properties", {}))
                    for entry in self.clipboard
                )
            ):
                parent_id = None
        # Build the target sibling list once so cascade pastes walk
        # a live view as each new clone lands — otherwise repeated
        # Ctrl+V would stack every clipboard entry at the same slot.
        target_siblings: list[WidgetNode] | None = None
        if base_position is None:
            if parent_id is None:
                target_siblings = self.active_document.root_widgets
            else:
                parent = self.get_widget(parent_id)
                target_siblings = parent.children if parent is not None else []
        new_top_ids: list[str] = []
        for idx, data in enumerate(self.clipboard):
            root = self._clone_with_fresh_ids(data)
            try:
                if base_position is not None:
                    bx, by = base_position
                    root.properties["x"] = max(0, int(bx) + idx * 20)
                    root.properties["y"] = max(0, int(by) + idx * 20)
                elif target_siblings is not None:
                    # Start at (10, 10) so container pastes sit near the
                    # Frame's top-left regardless of the source's coord
                    # space. find_free_cascade_slot walks the current
                    # sibling list, so each loop iteration sees the
                    # clones already pasted and picks the next slot.
                    nx, ny = find_free_cascade_slot(target_siblings)
                    root.properties["x"] = max(0, nx)
                    root.properties["y"] = max(0, ny)
                else:
                    root.properties["x"] = (
                        int(root.properties.get("x", 0)) + 20
                    )
                    root.properties["y"] = (
                        int(root.properties.get("y", 0)) + 20
                    )
            except (TypeError, ValueError):
                pass
            self._paste_recursive(root, parent_id)
            new_top_ids.append(root.id)
            # Pasted bindings carry the source-doc's UUIDs verbatim;
            # apply the requested migration policy so cross-doc
            # paste bindings either copy / move / unbind to match
            # the user's intent. ``var_policy=None`` opts out (the
            # caller already migrated through the dialog).
            if var_policy is not None:
                target_doc = self.find_document_for_widget(root.id)
                if target_doc is not None:
                    self.migrate_local_var_bindings(
                        root, target_doc,
                        source_policy=var_policy[0],
                        target_policy=var_policy[1],
                    )
        if new_top_ids:
            if len(new_top_ids) == 1:
                self.select_widget(new_top_ids[0])
            else:
                self.set_multi_selection(
                    set(new_top_ids), primary=new_top_ids[0],
                )
        return new_top_ids

    def _clone_with_fresh_ids(self, data: dict) -> WidgetNode:
        """Rebuild a WidgetNode from a `to_dict` snapshot, forcing a
        fresh UUID for every node in the subtree and clearing names
        so `add_widget` can auto-assign new ones."""
        node = WidgetNode(
            widget_type=data["widget_type"],
            properties=dict(data.get("properties", {})),
        )
        # node.id is already a fresh UUID from WidgetNode.__init__.
        node.name = ""  # let add_widget auto-name
        node.visible = bool(data.get("visible", True))
        node.locked = bool(data.get("locked", False))
        for child_data in data.get("children", []):
            child = self._clone_with_fresh_ids(child_data)
            child.parent = node
            node.children.append(child)
        return node

    def _paste_recursive(
        self, node: WidgetNode, parent_id: str | None,
    ) -> None:
        """Add `node` to the project under `parent_id`, then walk
        descendants. Mirrors `project_loader._add_recursive`: we
        temporarily detach children so `add_widget` only fires the
        event for `node`, then re-add each descendant explicitly so
        every subscriber sees them one by one."""
        children_copy = list(node.children)
        node.children = []
        node.parent = None
        self.add_widget(node, parent_id=parent_id)
        for child in children_copy:
            child.parent = None
            self._paste_recursive(child, parent_id=node.id)

    def duplicate_widget(
        self, widget_id: str, force_top_level: bool = False,
    ) -> str | None:
        node = self.get_widget(widget_id)
        if node is None:
            return None
        # Deep-clone the entire subtree (containers carry their children)
        # via the same fresh-id walk paste uses. Without this a Frame
        # duplicate landed empty — only the container shell got a clone.
        clone = self._clone_with_fresh_ids(node.to_dict())
        try:
            clone.properties["x"] = int(clone.properties.get("x", 0)) + 20
            clone.properties["y"] = int(clone.properties.get("y", 0)) + 20
        except (ValueError, TypeError):
            pass
        if force_top_level:
            parent_id: str | None = None
        else:
            parent_id = node.parent.id if node.parent else None
        self._paste_recursive(clone, parent_id)
        self.select_widget(clone.id)
        return clone.id

    def _reorder_to(
        self, widget_id: str,
        final_index: int | None, direction: str,
    ) -> None:
        """Shared body for every sibling-order mutation.

        ``final_index=None`` means "end of the list" (used by
        bring_to_front); an explicit integer is clamped to the valid
        range. ``direction`` rides on the ``widget_z_changed`` event
        so listeners can distinguish front / back / reorder for
        animation or history labelling.
        """
        node = self.get_widget(widget_id)
        if not isinstance(node, WidgetNode):
            return
        siblings = self._sibling_list(node)
        if not siblings:
            return
        try:
            old_index = siblings.index(node)
        except ValueError:
            return
        if final_index is None:
            final_index = len(siblings) - 1
        else:
            final_index = max(0, min(len(siblings) - 1, final_index))
        if final_index == old_index:
            return
        siblings.pop(old_index)
        siblings.insert(final_index, node)
        self.event_bus.publish("widget_z_changed", widget_id, direction)

    def reorder_child_at(
        self, widget_id: str, final_index: int,
    ) -> None:
        """Move a child to the exact ``final_index`` in its sibling
        list. Unlike ``reparent``, the index is the destination slot
        in the *result* list, not the pre-removal slot — callers
        working with visible positions (grid drag, list reorder)
        can pass the cursor-derived index directly without the
        compensation arithmetic ``reparent`` does.
        """
        self._reorder_to(widget_id, final_index, "reorder")

    def bring_to_front(self, widget_id: str) -> None:
        self._reorder_to(widget_id, None, "front")

    def send_to_back(self, widget_id: str) -> None:
        self._reorder_to(widget_id, 0, "back")
