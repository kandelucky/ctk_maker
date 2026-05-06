# Behavior Sidebar — Plan

**Status:** planned, not started
**Target version:** v1.13 / v1.14 (post-launch)
**Estimated effort:** ~2 days for v1, +3-4 days for v2

## Goal

Reverse lookup for behavior code: given a method in the per-window behavior file, show every widget that binds to it. Today the Properties panel only goes forward (widget → methods); this panel goes backward (method → widgets).

## Why

- **Refactoring confidence** — rename or delete a method, see all callers immediately.
- **Orphan visibility** — methods declared in the `.py` file that no widget binds to.
- **Dangling visibility** — widget bindings whose target method doesn't exist in the file.
- **Onboarding** — a new contributor sees a window's behavior surface in one panel.

Sits naturally next to the F11 Variables window — variables and references already share a docked panel; methods are the third axis.

## v1 — minimum viable (~2 days)

Read-only. Active document only. Single-file UI.

| Capability | Notes |
|---|---|
| List methods on the active document's behavior class | Source: `parse_handler_methods(file_path, class_name)` ([app/io/scripts.py:127](../../app/io/scripts.py#L127)) |
| Per method — list of widgets that bind it + the event key | Build reverse index by walking `Document.root_widgets` + each `WidgetNode.handlers` |
| Click a widget entry → select on canvas | Publish `selection_changed` via `Project.select_widget(widget_id)` |
| Click a method name → open in editor at that line | Reuse `launch_editor` + `parse_object_reference_fields`-style line lookup |
| Mark orphan methods (declared, never bound) | Method exists in `.py`, no widget references it |
| Mark dangling bindings (referenced by a widget, not declared) | Already collected by exporter as `_MISSING_BEHAVIOR_METHODS` — reuse |
| Live repaint on `widget_handler_changed` / `widget_added` / `widget_removed` / `active_document_changed` | Same subscription pattern as the existing Variables window |

### File-level plan

| File | Change |
|---|---|
| `app/ui/behavior_sidebar.py` | New — `BehaviorSidebarWindow(ctk.CTkToplevel)` mirroring `history_window.py` shape: ttk.Treeview, dark titlebar, persistent geometry. ~300 LOC estimate. |
| `app/ui/main_window.py` | Add F-key shortcut + menu entry to open the sidebar. ~10 LOC. |
| `app/io/scripts.py` | Add `find_method_definition_line(file_path, class_name, method_name) → int \| None` helper for editor jump (the existing `parse_handler_methods` only returns names). ~15 LOC. |
| `app/core/script_paths.py` | Already exposes `behavior_class_name` / `behavior_file_path` — no changes. |

### Behavior on edge cases

- **Project unsaved** (no `.ctkproj` path) → empty state: "Save the project to see its behavior file."
- **Behavior file missing** → empty state: "No behavior file yet. Bind a handler from the Properties panel to create one."
- **No methods + no bindings** → empty state with the same hint.
- **Document switch** → repaint with the new active doc's bindings.

## v2 — stretch (~3-4 days, optional)

Editing affordances. Cross-document view. Refactor support.

| Capability | Difficulty |
|---|---|
| **Cross-document view** — main + every Dialog in one tree, grouped by window | Medium. Need iteration over `project.documents`, group rendering. |
| **Right-click → Rename method** — rewrites file + updates every binding atomically | High. Needs file mutation + bulk `BindHandlerCommand`-style undo entry. |
| **Right-click → Delete method** — removes def from file + clears every binding | High. Confirms first; reuses existing `delete_method_from_file`. |
| **Right-click → Move to another window's behavior file** | High. File mutation across both files + bind retargeting. |
| **Search bar** — filter methods by substring | Low. Standard tkinter Entry + filter pass. |
| **Drag method onto widget on canvas** → bind | High. Cross-window drag from sidebar to canvas; new drop target on workspace. |

## Layout sketch

```
┌── Behavior — Login Page ─────────────────────[F9 to toggle]──┐
│ [Search methods...]                                          │
│                                                              │
│ ▼ on_submit                            (3 callers)           │
│     button_login           clicked                           │
│     button_save_continue   clicked                           │
│     entry_password         <Return>                          │
│                                                              │
│ ▼ on_cancel                            (1 caller)            │
│     button_cancel          clicked                           │
│                                                              │
│ ⚠ on_legacy_action                     orphan                │
│ ⚠ on_typo                              dangling — no def    │
│                                                              │
│ ────                                                         │
│ Edit behavior file…                                          │
└──────────────────────────────────────────────────────────────┘
```

Window-chrome buttons (top-right): refresh, open in editor, close. Bottom row: same "Edit behavior file…" affordance the Properties panel already offers (F7).

## Data flow

```
Open sidebar
  → read active_document.id
  → resolve behavior_file_path(project.path, doc)
  → parse_handler_methods(file_path, class_name) → list of method names
  → walk doc.root_widgets recursively
       collect (widget_id, widget_name, event_key, [method_names]) per binding
  → reverse-index: method_name → list[(widget, event)]
  → render tree: one node per method, children = widgets
  → mark orphans (in method list, no callers) and danglings
       (referenced by widget, not in method list)

On widget_handler_changed:
  → re-walk just that widget's handlers
  → diff vs cached reverse index
  → repaint affected method nodes only

On active_document_changed:
  → full rebuild for new doc
```

## Cross-references

- Builds on [EVENT_BUS.md — `widget_handler_changed`](../spec/EVENT_BUS.md)
- Reads from [DATA_MODEL.md — `WidgetNode.handlers`](../spec/DATA_MODEL.md)
- Reuses [`app/io/scripts.py`](../../app/io/scripts.py) parse + edit helpers (already battle-tested via Phase 2 + Object References)
- Sister panel to [`app/ui/variables_window.py`](../../app/ui/variables_window.py) — same ttk.Treeview pattern, same docking convention
- Compares to: VS Code "Find All References", Qt Designer "Signal/Slot Editor"

## Open questions

1. **F-key binding** — F9 looks free. Confirm before settling.
2. **Single-window or multi-window** — start single-window for v1; user feedback decides whether v2 cross-doc happens at all.
3. **Method ordering** — source-file order (line number) vs. alphabetical vs. binding-count? Source-file order is most intuitive for "open in editor" navigation.
4. **Orphan methods — soft-delete UX** — when shown, should the user be able to one-click delete? Phase 2's "delete method" dialog already exists; sidebar could deep-link into it.
5. **Window-level behavior** — currently a Window has its own behavior class but no events bound to itself. If Window events appear later (e.g. `on_window_close`), the sidebar already has the right grouping (the Window node IS a callable surface).

## Out of scope

- Method bodies preview / inline editing → use the editor (F7) instead.
- Variable / object-reference views → those live in F11.
- Cross-project search ("which projects use this method name") → projects don't share methods; method names are per-class scoped.
- Live runtime call graph → static analysis only; runtime instrumentation is a different product.

## Risks

- **Cache staleness** — file mutations from outside the builder (user edits in VS Code) won't fire `widget_handler_changed`. v1 mitigation: refresh button + window-focus event handler that re-parses the `.py` file. v2: filesystem watcher (same as the deferred "Live hot-reload preview" candidate).
- **Large windows** — a window with 200+ widgets and 30+ methods would render a ~230-row tree. Treeview handles that well; but rendering cost on every `widget_handler_changed` could feel sluggish. Mitigation: debounce repaints with `tk.after_idle`, same trick the Object Tree uses.
- **Test coverage** — UI panel testing is flaky on Tk; cover the reverse-index builder + orphan/dangling detection as pure functions in `tests/test_behavior_sidebar.py`. Skip Tk-driven tests.

## Acceptance — v1 ships when

- [ ] F9 (or chosen key) opens the sidebar.
- [ ] Active document's methods + their callers render correctly on a 5-method × 12-widget test fixture.
- [ ] Click-method opens the editor at the right line on at least 2 editor presets (VS Code + Notepad++).
- [ ] Click-widget moves the canvas selection.
- [ ] Orphan + dangling badges render correctly.
- [ ] Live repaint works when adding/removing/rebinding handlers from the Properties panel.
- [ ] Tests for the reverse-index function + orphan/dangling detection (≥6 cases).
