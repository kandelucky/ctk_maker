# CTkMaker — Event Bus

Pub/sub topology connecting model mutations to UI updates.

## API — [app/core/event_bus.py](../../app/core/event_bus.py)

15 lines. The whole class:

```python
class EventBus:
    def __init__(self):
        self._listeners: dict[str, list] = {}

    def subscribe(self, event: str, callback) -> None: ...
    def unsubscribe(self, event: str, callback) -> None: ...
    def publish(self, event: str, *args, **kwargs) -> None:
        for callback in list(self._listeners.get(event, [])):
            callback(*args, **kwargs)
```

Single instance per `Project`, exposed as `Project.event_bus`. Publish is synchronous — callbacks run inline. The `list(...)` snapshot in `publish` lets a callback unsubscribe itself (or others) without skipping later listeners.

No event introspection, no priority, no async. If an event fires no one cares about, nothing happens (default to empty listener list).

## Convention

- **Event names** — `lower_snake_case`. Past tense for state changes (`widget_added`, `selection_changed`); `request_*` prefix for UI-triggered actions handled elsewhere; `_request` suffix for canvas drop intents.
- **Payload** — positional `*args`. No `**kwargs` in current usage. Subscribers must match the signature exactly.
- **Reentrance** — safe to publish from inside a subscriber. Safe to subscribe/unsubscribe during dispatch.
- **Failure** — not caught at the bus level. A subscriber that raises will propagate up. Defensive try/except sits in the subscriber's own callback when needed.

## Channels by feature area

### Widget mutation

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `widget_added` | `(node: WidgetNode)` | [project.py:637](../../app/core/project.py#L637) | Any add — root or child. Fired AFTER the node is in the tree. |
| `widget_removed` | `(widget_id, parent_id)` | [project.py:656](../../app/core/project.py#L656) | Subtree-wide; fired once for the removed root. |
| `widget_reparented` | `(widget_id, old_parent_id, new_parent_id)` | [project.py:776](../../app/core/project.py#L776), drag.py | Cross-parent or to/from root. |
| `widget_z_changed` | `(widget_id, direction)` | [project.py:1793](../../app/core/project.py#L1793) | `direction` ∈ `"front" / "back" / "reorder"`. |
| `widget_renamed` | `(widget_id, new_name)` | [project.py:553](../../app/core/project.py#L553) | Special case: fires with `WINDOW_ID` when document is renamed. |
| `widget_visibility_changed` | `(widget_id, visible: bool)` | [project.py:1441](../../app/core/project.py#L1441) | |
| `widget_locked_changed` | `(widget_id, locked: bool)` | [project.py:1456](../../app/core/project.py#L1456) | |
| `widget_group_changed` | `(widget_id, group_id \| None)` | [project.py:1471](../../app/core/project.py#L1471) | Ctrl+G / Ctrl+Shift+G. |
| `widget_description_changed` | `(widget_id, new_description)` | commands.py, [panel.py:933](../../app/ui/properties_panel/panel.py#L933) | AI-bridge field. |
| `widget_handler_changed` | `(widget_id, event_key, method_name)` | commands.py (5 sites), workspace/core.py:2147, panel.py:1141 | Phase 2. `event_key` is `"command"` or `"bind:<seq>"`; `method_name` may be `None` for unbind. |
| `property_changed` | `(widget_id, prop_name, value)` | [project.py:923](../../app/core/project.py#L923) (and 4 more) | Also fires with `widget_id == WINDOW_ID` for window-level properties. |

### Document lifecycle

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `document_added` | `(doc_id)` | commands.py:1274, [main_window.py:1624](../../app/ui/main_window.py#L1624) | Triggers eager creation of the per-window behavior file. |
| `document_removed` | `(doc_id, doc_name)` | commands.py:1311, main_window.py:1675, chrome.py:720 | |
| `document_renamed` | `(doc_id, old_name, new_name)` | [project.py:558](../../app/core/project.py#L558) | Window rename — file + class rename in behavior file. |
| `document_resized` | `(width, height)` | [project.py:448](../../app/core/project.py#L448) | |
| `document_position_changed` | `(doc_id, x, y)` | commands.py:1245 | Canvas drag of a document. |
| `documents_reordered` | `()` | [project.py:404](../../app/core/project.py#L404) | Tab strip reorder. |
| `active_document_changed` | `(doc_id)` | project.py:360, project.py:372, project.py:403, commands.py:1275, project_loader.py:329, chrome.py:711 | Switches workspace + properties focus. |
| `document_collapsed_changed` | `(doc_id, collapsed: bool)` | [project.py](../../app/core/project.py) `set_document_collapsed` | Toggle ON destroys widgets via lifecycle + adds chip to the bottom tabs bar. Toggle OFF rebuilds widgets at the saved canvas position; an auto-shift moves the doc clear of any other doc that crept into its slot while it was minimised. |
| `document_ghost_changed` | `(doc_id, ghost: bool)` | [project.py](../../app/core/project.py) `set_document_ghost` | Toggle ON captures the doc's rect as a desaturated PIL screenshot via `GhostManager.freeze`, destroys widgets, places a single canvas image item. Toggle OFF deletes the image and rebuilds widgets via `lifecycle.create_widget_subtree`. |

### Variables

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `variable_added` | `(entry: VariableEntry)` | [project.py:1084](../../app/core/project.py#L1084), commands.py | Both globals and locals. |
| `variable_removed` | `(var_id)` | [project.py:1113](../../app/core/project.py#L1113) | |
| `variable_renamed` | `(var_id, new_name)` | [project.py:1133](../../app/core/project.py#L1133) | UUID stable; only display name changes. |
| `variable_type_changed` | `(var_id, new_type)` | [project.py:1153](../../app/core/project.py#L1153) | `new_type` ∈ `"str" / "int" / "float" / "bool" / "color"`. |
| `variable_default_changed` | `(var_id, new_default: str)` | [project.py:1175](../../app/core/project.py#L1175) | Wired bindings (`BINDING_WIRINGS` entries) update live via Tk's `textvariable` / `variable`. Cosmetic bindings (e.g. `fg_color`, `text_color`) are resolved as literals at build time, so `workspace.core` listens for this event and rebuilds the affected widget subtrees. |
| `local_variables_migrated` | `(count)` | [project.py:1391](../../app/core/project.py#L1391) | Cross-doc paste. Triggers MainWindow status toast. |

### Object References

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `object_reference_added` | `(entry: ObjectReferenceEntry)` | commands.py:1649, panel.py:1625, panel.py:1722, variables_window.py:1295 | |
| `object_reference_removed` | `(entry)` | commands.py:1636, panel.py:1677, variables_window.py:1545 | |
| `object_reference_renamed` | `(entry)` | commands.py:1708 | |
| `object_reference_target_changed` | `(entry)` | commands.py:1745, commands.py:1754 | Re-target via Variables window. |

### Selection + tools

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `selection_changed` | `(widget_id \| None \| display)` | [project.py:846](../../app/core/project.py#L846), project.py:873, widget_lifecycle.py:629 | `None` = nothing selected; multi-select sends a special display marker. |
| `tool_changed` | `(tool: str)` | [controls.py:340](../../app/ui/workspace/controls.py#L340) | Toolbar mode switch (select / pan / rectangle, etc.). |

### Undo / redo

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `history_changed` | `()` | [history.py:105](../../app/core/history.py#L105) | After every `push` / `undo` / `redo`. Drives History panel + main-window undo/redo button states. |

### Project state

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `dirty_changed` | `(is_dirty: bool)` | [main_window.py:739](../../app/ui/main_window.py#L739) + ~15 others | Fires whenever an unsaved change happens. Drives title-bar dirty marker. |
| `project_renamed` | `(new_name)` | main_window.py (4 sites), workspace/core.py:2326 | |
| `font_defaults_changed` | `(defaults: dict)` | panel_commit.py:479 + project_window.py (4 sites) | Cascade map for font resolution. |
| `component_library_changed` | `()` | workspace/core.py:2254, workspace/core.py:2400 | `.ctkcomp` added/removed in `<project>/components/`. |

### UI requests (UI → UI routing)

`request_*` events are intent signals — published by one UI component, handled by another. Not model state.

| Event | Payload | Published by | Subscriber |
|---|---|---|---|
| `request_preview` | `()` | controls.py:149 | MainWindow Ctrl+R / F5 handler |
| `request_preview_active` | `()` | controls.py:159 | Preview current document |
| `request_preview_dialog` | `(doc_id)` | chrome.py:611 | Preview a specific dialog |
| `request_add_dialog` | `()` | controls.py:284 | MainWindow → opens new-dialog flow |
| `request_edit_description` | `()` | workspace/core.py:2036, chrome.py:647 | Description editor dialog |
| `request_close_project` | `()` | chrome.py:683 | MainWindow close flow |
| `request_export_document` | `(doc_id)` | chrome.py:621 | Export single document |
| `request_open_variables_window` | `(scope, doc_id, variable_id=None)` | chrome.py:654, controls.py:287, panel.py:1811, panel_commit.py:192/203, panel_commit.py:_on_double_click (bound row) | F11 Variables window. `scope` ∈ `"global" / "local" / "objrefs"`. Optional `variable_id` pre-selects that row in the panel — used when the user double-clicks a variable-bound property. |
| `palette_drop_request` | `(...)` | palette.py:450 | Workspace canvas — handles dropped widget type |
| `component_drop_request` | `(...)` | components_panel.py | Workspace canvas — handles dropped `.ctkcomp` |

## Major subscribers

Where each major UI piece plugs into the bus. Use this to trace "what re-renders when X happens".

### Workspace canvas — [app/ui/workspace/core.py:248](../../app/ui/workspace/core.py#L248), [widget_lifecycle.py:82](../../app/ui/workspace/widget_lifecycle.py#L82)

```
property_changed              → re-render the affected widget
widget_added                  → seed binding cache + create canvas window
widget_removed                → drop binding cache + destroy canvas window
widget_reparented             → rebuild parent
widget_z_changed              → reorder canvas stacking
selection_changed             → update selection rect + handles
palette_drop_request          → instantiate dropped widget type
component_drop_request        → unzip + insert .ctkcomp
document_resized              → resize canvas frame
project_renamed               → update document chrome title
dirty_changed                 → update dirty marker
widget_renamed                → update on-canvas label fallbacks
documents_reordered           → reorder document chrome strip
```

### Properties panel — [app/ui/properties_panel/panel.py:148](../../app/ui/properties_panel/panel.py#L148)

```
selection_changed             → repopulate tree
tool_changed                  → enable/disable scope-based rows
property_changed              → refresh affected row's overlay
widget_renamed                → update header label
```

### Object Tree — `app/ui/object_tree_window.py`

Subscribes to widget add/remove/reparent/rename/visibility/locked/group/handler events to keep the tree mirrored.

### Variables window — `app/ui/variables_window.py`

Subscribes to all `variable_*` and `object_reference_*` events plus `active_document_changed` (to swap the Local tab).

### History panel — `app/ui/history_window.py`

Subscribes to `history_changed`. Repaints the timeline.

### Main window title — [main_window.py:627](../../app/ui/main_window.py#L627)

Subscribes to `dirty_changed`, `project_renamed`, `history_changed`. Title is the dirty/clean signal source.

## Sequencing patterns

**Mutation → render** is one-hop. The `Command` runs on the model, the model publishes, the workspace re-renders. No coalescing.

**Compound mutations** (e.g. reparent) publish multiple events in one call. Subscribers should be idempotent — receiving `widget_reparented` followed by `property_changed` for repositioned children is normal.

**Loading a project** publishes a flurry: per-document `active_document_changed`, then individual events for any post-load migration (e.g. `local_variables_migrated`). UI panels that subscribe in `__init__` need to be ready for events before their constructor returns.

## Patterns to avoid

- **Cross-class state via the bus.** The bus is for "X happened, anyone interested?", not "fetch me Y." Reading state lives on `Project` directly.
- **High-frequency publish.** Per-pixel drag updates do not go through the bus — workspace renders directly. Only the final commit (mouse-up) publishes `property_changed`.
- **Async / threaded callbacks.** All Tk callbacks are main-thread. The bus is not thread-safe; cross-thread work must use `tk.after`.
