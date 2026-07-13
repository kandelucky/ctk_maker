# CTkMaker — Event Bus

Pub/sub topology connecting model mutations to UI updates.

## API — [app/core/event_bus.py](../../app/core/event_bus.py)

14 lines. The whole class:

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
| `widget_added` | `(node: WidgetNode)` | [project.py:773](../../app/core/project.py#L773) | Any add — root or child. Fired AFTER the node is in the tree. |
| `widget_removed` | `(widget_id, parent_id)` | [project.py:792](../../app/core/project.py#L792) | Subtree-wide; fired once for the removed root. |
| `widget_reparented` | `(widget_id, old_parent_id, new_parent_id)` | [project.py:912](../../app/core/project.py#L912), workspace/drag_reparent.py (6 sites) | Cross-parent or to/from root. |
| `widget_z_changed` | `(widget_id, direction)` | [project.py:1930](../../app/core/project.py#L1930) | `direction` ∈ `"front" / "back" / "reorder"`. |
| `widget_renamed` | `(widget_id, new_name)` | [project.py:689](../../app/core/project.py#L689), [:704](../../app/core/project.py#L704) | Special case: fires with `WINDOW_ID` when document is renamed. |
| `widget_visibility_changed` | `(widget_id, visible: bool)` | [project.py:1578](../../app/core/project.py#L1578) | |
| `widget_locked_changed` | `(widget_id, locked: bool)` | [project.py:1593](../../app/core/project.py#L1593) | |
| `widget_group_changed` | `(widget_id, group_id \| None)` | [project.py:1609](../../app/core/project.py#L1609) | Ctrl+G / Ctrl+Shift+G. |
| `widget_description_changed` | `(widget_id, new_description)` | commands/properties.py:100, [panel.py:1104](../../app/ui/properties_panel/panel.py#L1104) | AI-bridge field. |
| `widget_handler_changed` | `(widget_id, event_key, method_name)` | commands/handlers.py (9 sites), panel.py:1375/1474/1541, panel_schema.py:1153 | `event_key` is `"command"` or `"bind:<seq>"`; empty `method_name` for unbind / pending. |
| `property_changed` | `(widget_id, prop_name, value)` | [project.py:1059](../../app/core/project.py#L1059) (and 5 more), workspace/drag_release.py:149 | Also fires with `widget_id == WINDOW_ID` for window-level properties. |

### Document lifecycle

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `document_added` | `(doc_id)` | commands/documents.py:31, [main_documents.py:140](../../app/ui/main_documents.py#L140) | Refreshes the pages + asset trees; auto-saves. |
| `document_removed` | `(doc_id, doc_name)` | commands/documents.py:68 | |
| `document_renamed` | `(doc_id, old_name, new_name)` | [project.py:695](../../app/core/project.py#L695) | Window rename. |
| `document_resized` | `(width, height)` | [project.py:584](../../app/core/project.py#L584) | |
| `document_position_changed` | `(doc_id, x, y)` | commands/documents.py (4 sites), workspace/controls.py:375, workspace/chrome_removal.py:64 | Canvas drag of a document. |
| `documents_reordered` | `()` | [project.py:540](../../app/core/project.py#L540) | Tab strip reorder. |
| `active_document_changed` | `(doc_id)` | project.py:355 / :508 / :539, commands/documents.py:32 | Switches workspace + properties focus. |
| `document_collapsed_changed` | `(doc_id, collapsed: bool)` | [project.py:414](../../app/core/project.py#L414) `set_document_collapsed` | Toggle ON destroys widgets via lifecycle + adds chip to the bottom tabs bar. Toggle OFF rebuilds widgets at the saved canvas position; an auto-shift moves the doc clear of any other doc that crept into its slot while it was minimised. |
| `document_ghost_changed` | `(doc_id, ghost: bool)` | [project.py:460](../../app/core/project.py#L460) `set_document_ghost` | Toggle ON captures the doc's rect as a desaturated PIL screenshot via `GhostManager.freeze`, caches it on `Document._cached_ghost_pil`, destroys widgets, places a single canvas image item. Toggle OFF deletes the image and rebuilds widgets via `lifecycle.create_widget_subtree`. Two subscribers: workspace `_on_document_ghost_changed` redraws so the ghost statusbar repaints; `FilesMixin._on_ghost_toggled_save` (main_files.py) writes `.ctkproj` immediately so the base64 screenshot survives close-without-save. Load-time `freeze_pending` deliberately bypasses this event (uses `freeze_from_cache` + direct redraw) so restoring N ghosts doesn't trigger N re-saves. UI entry point: click the strip below the doc rect, or click anywhere on the screenshot when ghosted (two-step: first click focuses, second click unghosts). |

### Variables

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `variable_added` | `(entry: VariableEntry)` | [project.py:1221](../../app/core/project.py#L1221), commands/variables.py:67 / :105 | Both globals and locals. |
| `variable_removed` | `(var_id)` | [project.py:1250](../../app/core/project.py#L1250) | |
| `variable_renamed` | `(var_id, new_name)` | [project.py:1270](../../app/core/project.py#L1270) | UUID stable; only display name changes. |
| `variable_type_changed` | `(var_id, new_type)` | [project.py:1290](../../app/core/project.py#L1290) | `new_type` ∈ `"str" / "int" / "float" / "bool" / "color"`. |
| `variable_default_changed` | `(var_id, new_default: str)` | [project.py:1312](../../app/core/project.py#L1312) | Wired bindings (`BINDING_WIRINGS` entries) update live via Tk's `textvariable` / `variable`. Cosmetic bindings (e.g. `fg_color`, `text_color`) are resolved as literals at build time, so `workspace.core` listens for this event and rebuilds the affected widget subtrees. |
| `local_variables_migrated` | `(count)` | [project.py:1528](../../app/core/project.py#L1528) | Cross-doc paste. Triggers MainWindow status toast. |

### Selection + tools

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `selection_changed` | `(widget_id \| None \| display)` | [project.py:982](../../app/core/project.py#L982), project.py:1009, widget_lifecycle.py:661 | `None` = nothing selected; multi-select sends a special display marker. |
| `tool_changed` | `(tool: str)` | [controls.py:450](../../app/ui/workspace/controls.py#L450) | Toolbar mode switch (select / pan / rectangle, etc.). |

### Undo / redo

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `history_changed` | `()` | [history.py:105](../../app/core/history.py#L105) | After every `push` / `undo` / `redo`. Drives History panel + main-window undo/redo button states. |

### Project state

| Event | Payload | Published by | Notes |
|---|---|---|---|
| `dirty_changed` | `(is_dirty: bool)` | [main_window.py:923](../../app/ui/main_window.py#L923) + ~15 others | Fires whenever an unsaved change happens. Drives title-bar dirty marker. |
| `project_renamed` | `(new_name)` | main_files.py:139, main_documents.py (3 sites) | |
| `font_defaults_changed` | `(defaults: dict)` | panel_commit.py:551 + project_window.py | Cascade map for font resolution. |
| `component_library_changed` | `()` | workspace/context_menu.py:614, :761 | `.ctkcomp` added/removed in `<project>/components/`. |

### UI requests (UI → UI routing)

`request_*` events are intent signals — published by one UI component, handled by another. Not model state.

| Event | Payload | Published by | Subscriber |
|---|---|---|---|
| `request_preview` | `()` | controls.py:158 | MainWindow Ctrl+R / F5 handler |
| `request_preview_active` | `()` | controls.py:167 | Preview current document |
| `request_preview_dialog` | `(doc_id)` | workspace/chrome_buttons.py:48 | Preview a specific dialog |
| `request_add_dialog` | `()` | controls.py:310 | MainWindow → opens new-dialog flow |
| `request_edit_description` | `()` | workspace/context_menu.py:370, workspace/chrome_buttons.py:83 | Description editor dialog |
| `request_close_project` | `()` | workspace/chrome_buttons.py:128, workspace/collapsed_tabs_bar.py:210 | MainWindow close flow |
| `request_export_document` | `(doc_id)` | workspace/chrome_buttons.py:58 | Export single document |
| `request_open_variables_window` | `(scope, doc_id, variable_id=None)` | workspace/chrome_buttons.py:91, controls.py:314, panel.py:1759, panel_commit.py:231/:262 | F11 Variables window. `scope` ∈ `"global" / "local"`. Optional `variable_id` pre-selects that row in the panel — used when the user double-clicks a variable-bound property. |
| `palette_drop_request` | `(...)` | palette.py:451 | Workspace canvas — handles dropped widget type |
| `component_drop_request` | `(...)` | components_panel.py | Workspace canvas — handles dropped `.ctkcomp` |

## Major subscribers

Where each major UI piece plugs into the bus. Use this to trace "what re-renders when X happens".

### Workspace canvas — [app/ui/workspace/core.py:286](../../app/ui/workspace/core.py#L286), [widget_lifecycle.py:84](../../app/ui/workspace/widget_lifecycle.py#L84)

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

### Properties panel — [app/ui/properties_panel/panel.py:176](../../app/ui/properties_panel/panel.py#L176)

```
selection_changed                    → repopulate tree
tool_changed                         → enable/disable scope-based rows
property_changed                     → refresh affected row's overlay
widget_renamed                       → update header label
```

### Object Tree — `app/ui/object_tree_window.py`

Subscribes to widget add/remove/reparent/rename/visibility/locked/group/handler events to keep the tree mirrored.

### Variables window — `app/ui/variables_window.py`

Subscribes to all `variable_*` events plus `active_document_changed` (to swap the Local tab).

### History panel — `app/ui/history_window.py`

Subscribes to `history_changed`. Repaints the timeline.

### Main window title — [main_window.py:804](../../app/ui/main_window.py#L804)

Subscribes to `dirty_changed`, `project_renamed`, `history_changed`. Title is the dirty/clean signal source.

## Sequencing patterns

**Mutation → render** is one-hop. The `Command` runs on the model, the model publishes, the workspace re-renders. No coalescing.

**Compound mutations** (e.g. reparent) publish multiple events in one call. Subscribers should be idempotent — receiving `widget_reparented` followed by `property_changed` for repositioned children is normal.

**Loading a project** publishes a flurry: per-document `active_document_changed`, then individual events for any post-load migration (e.g. `local_variables_migrated`). UI panels that subscribe in `__init__` need to be ready for events before their constructor returns.

## Patterns to avoid

- **Cross-class state via the bus.** The bus is for "X happened, anyone interested?", not "fetch me Y." Reading state lives on `Project` directly.
- **High-frequency publish.** Per-pixel drag updates do not go through the bus — workspace renders directly. Only the final commit (mouse-up) publishes `property_changed`.
- **Async / threaded callbacks.** All Tk callbacks are main-thread. The bus is not thread-safe; cross-thread work must use `tk.after`.
