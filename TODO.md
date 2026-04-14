# TODO / Roadmap

> Personal task list. Edit freely — add, remove, reorder, mark `[x]` when done.
> Format: standard GitHub markdown checkboxes. Works in any editor.

---

## Reference: Qt Designer (classic)

> **Design direction**: we are cloning Qt Designer's widget-based UX for CustomTkinter.
> Qt Designer is the 20-year-old battle-tested UI designer for Qt widgets — same mental model
> as ours (place widget → edit properties → export code). We explicitly **NOT** cloning
> Qt Design Studio (QML-based, declarative, states/timelines — overkill for CTk which is imperative).
>
> Docs: https://doc.qt.io/qt-6/qtdesigner-manual.html

### Qt Designer features mapped to our phases

- [x] **Three-panel layout** (Widget Box / Workspace / Property Editor) — Phase 0 ✅
- [x] **Drag-to-add from palette** — Phase 1 ✅
- [x] **Click-to-select with resize handles** — Phase 1 ✅
- [x] **Property editor with grouped sections** — Phase 0.5 ✅
- [ ] **Toolbar** (New / Open / Save / Preview / Export) — Phase 2
- [ ] **Object Inspector** (hierarchical widget tree panel) — Phase 7
- [ ] **Layout managers** (pack / grid / place) with visual indicator — Phase 6
- [ ] **Preview mode** — separate window running the generated app — Phase 2
- [ ] **Collapsible property groups** — Phase 0.5
- [ ] **Alignment tools** (align left/right/center when multi-selection) — Phase 7
- [ ] **Tab order editor** — Phase 8
- [ ] **Snap-to-grid + alignment guides** — Phase 7
- [ ] **Signal/Slot editor** → our "event handlers" — Phase 8
- [ ] **Resource editor** (assets management) — Phase 7
- [ ] **Form layouts** (rowspan/colspan/sticky in grid) — Phase 6

### Qt Designer features we explicitly skip

- ❌ Style sheet editor — CTk doesn't use CSS-like stylesheets
- ❌ Action editor (toolbars/menus) — CTk has no menu system by default
- ❌ Buddy editor (label→widget association) — not a CTk concept
- ❌ Docked panels — we use a fixed 3-panel layout

### TODO: study Qt Designer live

- [ ] Install Qt (Maintenance Tool or community installer), open `designer.exe`
- [ ] Spend 10 min placing widgets, editing properties, saving/opening a `.ui` file
- [ ] Screenshots of each window/panel for reference
- [ ] Note: which UX bits feel good, which feel dated — we copy the good, modernize the dated

---

## Icon library: Lucide Icons

> **Library**: https://lucide.dev — MIT, 1500+ outline icons
>
> **Workflow**: Claude lists the icons needed for each Phase 2+ feature. User manually downloads PNGs from lucide.dev and places them in `app/assets/icons/`. Claude does not download.
>
> **Fixed parameters** (set 2026-04-13 on first icon selection — all future icons must match):
>
> - **Render size**: **16 × 16** px
> - **Stroke width**: **2** (Lucide default)
> - **Color**: **#888888** (baked into PNG — dark theme subtle gray, matches group-header text color)
> - **Format**: PNG with RGBA alpha channel
>
> Helper: `app/ui/icons.py` → `load_icon(name, size=16) -> CTkImage`. Cached after first load.
>
> ### Icons already downloaded
>
> - [x] `chevron-down.png` — expanded/open disclosure
> - [x] `chevron-right.png` — collapsed/closed disclosure

---

## Phase 0 — MVP

- [x] Three-panel layout (palette / workspace / properties)
- [x] Event bus + Project model + WidgetNode
- [x] Widget descriptor pattern + registry
- [x] CTkButton descriptor (first one)
- [x] Click-to-add palette → workspace
- [x] Click-to-select + selection rectangle
- [x] Live property editing (string / number / color)
- [x] GitHub repo
- [x] Desktop shortcut (run.bat + .lnk)

---

## Phase 0.5 — Property Editor Enhancements

- [x] Drag-to-scrub on number labels (Blender / Photoshop style)
- [x] Alt-key for slow / fine scrub mode
- [x] Min / max constraints on numeric properties (clamped during drag)
- [x] Dynamic max via lambda (e.g. corner_radius capped at min(w,h)/2)
- [x] `transform_properties` hook in WidgetDescriptor (path → CTkImage)
- [x] Anchor editor — 3×3 grid for text / image alignment
- [x] Compound editor — image position dropdown (top / left / right / bottom)
- [x] Image picker editor — Browse / Clear with file dialog
- [x] Pillow dependency for image loading
- [x] Property groups with section headers (Position / Size / Colors / Text / Image & Alignment)
- [x] Subgroups inside groups (Character / Paragraph nested under Text)
- [x] Paired layout — X+Y, W+H, Radius+Border, BG+Hover, Size+Best Fit side by side
- [x] Per-prop `label_width` override in schema (for longer labels in compact pairs)
- [x] Compact font sizes and reduced row padding
- [x] Fixed-height labels + small row pady (visual breathing without elongation)
- [x] Property panel auto-syncs editor vars on `property_changed` (for live drag updates)
- [x] Boolean editor — CTkCheckBox with optional inline text label (e.g. `[☐] Bold`)
- [x] Multi-line text editor — CTkTextbox with border, ~3 visible lines, word wrap
- [x] Color buttons with visible border for fg contrast
- [x] Font size, font bold, font autofit (Best Fit) properties for CTkButton
- [x] Auto-fit text sizing — binary search algorithm computes max size that fits w×h
- [x] `derived_triggers` + `compute_derived` hook in WidgetDescriptor (for autofit)
- [x] `disabled_when` schema field (greys out font_size when autofit is on)
- [x] More vertical spacing between groups (12px gap above each group header)
- [x] Custom Photoshop-style color picker — sat/val square + hue slider + hex input + Old/New comparison
- [x] HSL Lightness slider (black → color → white range, syncs with HSV state)
- [x] Tint strip — 13 swatches showing variations of current color (centered Lightness range, width 0.5)
- [x] Tint strip width matches sliders exactly (DPI-aware, no borders, flush)
- [x] Saved Colors row with + button (max 20 entries, 2 rows × 10, square swatches)
- [x] Selection highlight on saved color swatch matching current pick (white border)
- [x] JSON persistence for saved colors at `~/.ctk_visual_builder/recent_colors.json`
- [x] `ColorHistory` singleton for tracking recent / saved colors
- [x] PIL-based HSV / HSL gradient generation (low-res render + bilinear upscale, ~28ms per redraw)
- [x] DPI-aware Canvas widgets — scale tk.Canvas to match CTk widget DPI scaling
- [x] `round()` instead of `int()` for float→hex conversion (fixes saved color highlight matching after round-trip)
- [x] Persistent recent slots (no destroy/recreate) — eliminates flicker when adding to saved
- [x] Rectangular borders on canvas via `highlightthickness` (no rounded wrapper conflict)
- [x] Layout reorder — New/Old comparison at top, then tint strip, then SV / sliders / hex / saved / OK
- [x] OK-only dialog (Cancel removed, X / Esc still cancel)
- [ ] Reset-to-default button per property
- [ ] Tooltip / hint when hovering over property labels
- [ ] Collapsible property groups
- [ ] Numeric editor: arrow keys (↑/↓ = ±1, Shift+↑/↓ = ±10)

---

## Phase 1 — Core Interactions ✅

- [x] Drag-to-move widgets on the canvas (offset-based, click-vs-drag threshold)
- [x] x / y as editable position properties (live sync with canvas drag)
- [x] Resize handles (8 corner/edge handles around selection, min 20×20)
- [x] Per-handle resize cursors (↔ ↕ ⤡ ⤢ via `sb_h_double_arrow` / `sb_v_double_arrow` / `size_nw_se` / `size_ne_sw`)
- [x] Delete key → remove selected widget (with confirmation dialog)
- [x] Right-click context menu (Duplicate, Delete, Bring to Front, Send to Back)
- [x] Esc key → deselect
- [x] Real drag-and-drop from palette (ghost preview, drop on canvas, click fallback)
- [x] Arrow keys to nudge selected widget (1px, Shift+arrow = 10px, focus-aware)
- [x] Cursor change to "fleur" / move icon when hovering a widget
- [x] Bring to Front / Send to Back via `widget.lift/lower` (canvas tag_raise doesn't work for embedded widgets)
- [x] Drag perf — skip selection rebuild during drag/resize, skip property panel rebuild on same selection
- [x] Window centered on screen (no off-screen bottom)
- [x] Color picker dialog clamped to visible screen area (ctk-tint-color-picker v0.3.2)
- [x] Replaced embedded color picker with PyPI `ctk-tint-color-picker` (576 lines removed)

---

## Phase 2 — Toolbar + Persistence + Menubar ✅

- [x] Toolbar component at the top (icons + labels) — `app/ui/toolbar.py`
- [x] New project (clear workspace) with confirm dialog
- [x] Save project → JSON file (`app/io/project_saver.py`), `.ctkproj` format with `version: 1`
- [x] Open project ← JSON file (`app/io/project_loader.py`) with `ProjectLoadError` + user-facing error dialogs
- [x] Export to Python — clean .py output (`app/io/code_exporter.py`) using descriptor conventions (`_NODE_ONLY_KEYS`, `_FONT_KEYS`, image handling)
- [x] Preview — subprocess-based, writes to tempdir, launches `python preview.py` in separate process (true preview = reality)
- [x] Light / Dark / System theme toggle — persistent at `~/.ctk_visual_builder/settings.json`, applied on startup
- [x] **Help (?) icon in Properties panel header** — opens `https://github.com/kandelucky/ctk_visual_builder/blob/main/docs/widgets/{slug}.md` for the selected widget type (camelCase → snake_case conversion)
- [x] **Menubar** (File / Form / Settings / Help) with dark theme styling, Lucide icons, 11pt font
- [x] **Recent Forms** tracking at `~/.ctk_visual_builder/recent.json` (max 10, newest first, dedup via `Path.resolve()`)
- [x] Keyboard shortcuts: Ctrl+N/O/S/Shift+S/R/W/Q
- [x] Current-project-path tracking (`_current_path`) — Save overwrites when known, else falls back to Save As dialog
- [x] Save As... separate command (`Ctrl+Shift+S`)
- [x] Widget Documentation menu item → opens GitHub docs in default browser
- [x] About dialog with dependency list
- [x] `app/core/recent_files.py`, `app/core/settings.py`, `app/io/` package with `project_saver`, `project_loader`, `code_exporter`

---

## Phase 2.5 — Palette / Widget Box polish ✅

- [x] Qt Designer-style **Widget Box** layout — `app/ui/palette.py` rewrite
- [x] Realtime **Filter** entry (CTkEntry with `trace_add`)
- [x] Collapsible groups with chevron: Buttons / Inputs / Containers / Display
- [x] Rows: `[icon] label` with Lucide icons per widget type
- [x] Unimplemented widgets rendered as **placeholder rows** (dimmed, no click/drag) so the full CTk roadmap is visible at a glance
- [x] Filter auto-expands all groups while active, collapses back to saved state when cleared
- [x] Hover highlight on real (implemented) items only

---

## Phase 3 — Widget Descriptors (2 / 15 done)

- [x] CTkButton (Phase 0)
- [x] CTkLabel — Geometry + Text (Style/Alignment/Color), transparent bg, justify + wraplength editor
- [x] CTkFrame — Geometry + Rectangle (Corners + Border) + Main Colors
- [x] **Font Decoration** (Underline + Strike) added to CTkButton + CTkLabel via CTkFont(underline, overstrike)
- [ ] CTkEntry
- [ ] CTkSlider
- [ ] CTkSwitch
- [ ] CTkProgressBar
- [ ] CTkComboBox
- [ ] CTkOptionMenu
- [ ] CTkSegmentedButton
- [ ] CTkCheckBox
- [ ] CTkRadioButton
- [ ] CTkTextbox
- [ ] CTkScrollableFrame
- [ ] CTkTabview
- [ ] Per-widget docs page under `docs/widgets/ctk_*.md` for each new descriptor (help icon already wired)
- [ ] **Perf check**: naive `disabled_when` re-evaluation in properties_panel `_on_property_changed` iterates all props on every change. For 15 widgets × ~5 disabled_when lambdas each, measure drag-time overhead. If noticeable, switch to dep-map approach (`TrackingDict` auto-detects which properties a lambda reads, builds `{trigger_prop: [dependent_props]}` map at rebuild time, so most changes hit O(1) dict lookup instead of O(N) re-evaluation).

---

## Phase 2.7 — Workspace Canvas + Editor UX ✅

- [x] **Fixed-size document rectangle** on canvas — framed, grid inside only, canvas background darker around document (CANVAS_OUTSIDE_BG / DOCUMENT_BG / DOCUMENT_PADDING)
- [x] Horizontal + vertical **CTk-styled scrollbars** (thin 10px, `#1a1a1a` track / `#3a3a3a` thumb), dynamic scrollregion
- [x] **Dot grid** (1px dots at 20px spacing, scales with zoom, drawn only inside document)
- [x] **Zoom** 25% → 400%: Ctrl+= / Ctrl+- / Ctrl+0 / Ctrl+MouseWheel, snap levels, selection controller takes `zoom_provider` callable and scales mouse deltas during resize
- [x] Coordinate helpers: `_logical_to_canvas`, `_canvas_to_logical`, `_screen_to_canvas` (scroll-aware via `canvas.canvasx/canvasy`)
- [x] Node properties stay in **logical coordinates** (zoom-independent source of truth)
- [x] **Top toolbar** — Select (V) / Hand (H) mode buttons, active highlight, Photoshop-style cursors
- [x] **Hand tool pan** via `canvas.scan_mark/scan_dragto`, works on both empty canvas and on top of widgets
- [x] **Middle-mouse pan** — works in any tool (Figma/Blender convention), Hand icon temporarily highlights during MMB press
- [x] **Bottom status bar** — `[−] [+] [NN% ▼]` zoom controls, live-updating label, dropdown with presets + `Fit to window` + `Actual size`
- [x] **Zoom warning** — yellow `⚠ Not actual size — set 100% for real preview` appears when zoom ≠ 100%
- [x] **Font scaling with zoom** — `_build_scaled_font(properties)` helper recreates CTkFont with `font_size * zoom` so text keeps up with widget geometry (minimum 6pt, integer rounded). Logical `font_size` in `node.properties` stays unchanged so export is zoom-independent.
- [x] `document_resized` event + matching handler; exporter reads doc size

---

## Phase 2.8 — Startup dialog + File → New rewrite ✅

- [x] **Startup dialog** on app launch — split Recent / New Project layout
- [x] **Recent Projects list** with relative timestamps (`Xm/h/d/w/mo/y ago`), click to select, double-click to open, right-click → Remove from Recent
- [x] `recent_files.remove_recent(path)` helper
- [x] **New Project form** (shared between startup and File → New): Name, Save to (+ folder picker), Device (Desktop/Mobile/Tablet/Custom), Screen Size (15+ modern presets including iPhone 15 Pro Max, iPad Pro 13, Galaxy S24 Ultra, Full HD / QHD / 4K UHD), Width, Height
- [x] **Validation**: empty / forbidden filename chars (`\\ / : * ? " < > |`) / existing file → red border + `self.bell()` + `messagebox.showwarning` with the full character list
- [x] **Immediate save** on Create — empty `.ctkproj` written to disk so Recent list tracks it
- [x] `Project.name` attribute persisted to `.ctkproj` JSON
- [x] File → New uses the same rich dialog (`dialogs.py` rewrite), with `default_save_dir` pointing at the current project's parent folder when one is loaded

---

## Phase 2.9 — Dirty tracking + quality of life ✅

- [x] MainWindow subscribes to `widget_added / widget_removed / property_changed / widget_z_changed / document_resized` to flip a `_dirty` flag
- [x] Title refresh shows `— name •` when unsaved; bullet disappears on save / load
- [x] `_confirm_discard_if_dirty()` → Yes (save) / No (discard) / Cancel dialog with `self.bell()` + `icon="warning"`
- [x] Wired to WM_DELETE_WINDOW (X button), File → New, File → Open, File → Close Project, File → Quit
- [x] **Georgian font rendering** — `ctk.ThemeManager.theme["CTkFont"]["family"] = "Segoe UI"` on Windows, plus `tkfont.nametofont(...).configure(family="Segoe UI")` for every named Tk font, plus a bulk replacement of `font=("", N)` → `font=("Segoe UI", N)` across palette / dialogs / properties_panel / startup_dialog (CTkFont's None-fallback doesn't trigger for `family=""`, so explicit family was required)
- [x] **Non-Latin keyboard layout shortcut fallback** — `bind_all("<Control-KeyPress>")` routes by hardware keycode so Ctrl+V/C/X/A and Ctrl+S/N/O/W/Q/R keep working under Georgian/Russian layouts where the Latin keysym is remapped
- [ ] **Georgian keyboard input** — known tkinter/Windows IME bug (bpo-46052), typing Georgian into an Entry yields `?` — paste works, direct typing does not. Real fix requires a non-tkinter UI toolkit (PyQt6, Flet, wxPython). Not scheduled.

---

## Phase 2.10 — Refactor + icon system (2026-04-14) ✅

- [x] **Extract `NewProjectForm`** (`app/ui/new_project_form.py`, 306 lines) — shared form component used by both StartupDialog and File → New. Constants (SCREEN_SIZES_BY_DEVICE, FORBIDDEN_NAME_CHARS, …), form builders, and `validate_and_get()` all live here.
- [x] **Extract `RecentList`** (`app/ui/recent_list.py`, 209 lines) — reusable scrollable recent list with relative timestamps, click-to-select, double-click to open, right-click → Remove from Recent, and `on_select` / `on_activate` callbacks.
- [x] `StartupDialog` shrunk **563 → 184 lines** (-67%), composes RecentList + NewProjectForm.
- [x] `dialogs.py` shrunk **300 → 90 lines** (-70%), wraps NewProjectForm as File → New modal.
- [x] **Workspace in-place refactor** — module + class docstrings, section headers, `__init__` split into `_init_state / _build_tool_bar / _build_status_bar / _build_canvas / _subscribe_events`, dead code removed (`_zoom_label`, `TOOL_BTN_FG`), magic string `"hand2"` → `TOOL_CURSORS[TOOL_HAND]`, `_set_zoom_fit_window` moved to Zoom section, `_on_canvas_click/motion/release` grouped at the bottom as "Canvas mouse events", outdated `Select / Hand / Zoom` comment fixed.
- [x] **Toolbar Qt Designer-style rewrite** — icon-only, 26×26 square buttons, hover tooltips with delayed popup (vanilla tk.Toplevel, 500ms delay, dark theme), separator support. Currently slimmed to New / Open / Save only until more actions need quick access.
- [x] **Icon tinting system** — `load_icon(name, size, color)` and `load_tk_icon(name, size, color)` now recolor every non-transparent pixel via PIL `Image.composite` on alpha mask. Cache keyed by `(name, size, color)`. Default color `#888888` preserves the old baked look; toolbar calls with `color="#cccccc"` for a brighter read on the dark bar.
- [x] **Fresh Lucide icon set** — re-downloaded 1943 PNGs via `tools/download.mjs` (Node + sharp) at 24×24 white. All 40 icons currently used by the builder replaced from the new source.

---

## Phase 4 — Undo / Redo

- [ ] `commands/base.py` — Command base class
- [ ] `commands/history.py` — undo/redo stacks
- [ ] AddWidgetCommand
- [ ] DeleteWidgetCommand
- [ ] MoveWidgetCommand
- [ ] ResizeWidgetCommand
- [ ] ChangePropertyCommand
- [ ] Ctrl+Z / Ctrl+Y keyboard shortcuts
- [ ] Toolbar undo/redo buttons

---

## Phase 5 — Window Settings

- [ ] Window settings panel (separate tab or area)
- [ ] Target window title
- [ ] Target window size (width, height)
- [ ] `overrideredirect` (frameless)
- [ ] `resizable` toggle
- [ ] Background color (`fg_color`)
- [ ] `appearance_mode` (system / light / dark)

---

## Phase 6 — Widget Nesting + Layout Managers

### Phase 6.1 — Tree data model ✅

- [x] `WidgetNode` parent/children graph (was half-present from `from_dict`)
- [x] `Project.add_widget(node, parent_id=None)` — default `None` = top-level, preserves old API
- [x] `Project.remove_widget` depth-first, removes subtree before emitting `widget_removed`
- [x] `Project.reparent(widget_id, new_parent_id)` with cycle detection (`_is_descendant`)
- [x] `Project.iter_all_widgets()` DFS generator
- [x] `Project.get_widget` walks the full tree, not just roots
- [x] `Project.duplicate_widget` clones into the same parent
- [x] `bring_to_front / send_to_back` operate within the sibling list only
- [x] New event-bus event: `widget_reparented(widget_id, old_parent_id, new_parent_id)`

### Phase 6.2 — Hierarchical rendering ✅

- [x] `SelectionController._selected_bbox` computes canvas-coord bbox from `winfo_rootx/rooty` — works for canvas children **and** nested children uniformly
- [x] `_on_widget_added` branches on `node.parent`: top-level → `canvas.create_window`, nested → `widget.place(x=, y=)` inside the parent widget
- [x] `_apply_zoom_to_widget` branches on `window_id is None`: canvas children use `canvas.coords`, nested use `widget.place_configure` in local coords
- [x] `_on_property_changed` x/y handles both modes
- [x] `_on_widget_removed` guards `canvas.delete(None)`
- [x] Drag math rewritten to **delta-based** (`new_x = start_x + int(mouse_delta_root / zoom)`) — works for canvas children and nested children without coord-space conversion
- [x] `project_loader._add_recursive` re-emits `widget_added` events for every descendant so the workspace actually renders nested trees loaded from disk
- [x] **Z-order fix**: `widget.lower()` pushed nested children behind CTkFrame's internal drawing canvas forever; replaced with re-`lift()` of every sibling in project-tree order so stacking matches the model without ever touching CTk internals
- [x] **Selection handles + rectangle as embedded tk.Frame widgets** via `canvas.create_window` + `.lift()` so they are never hidden behind overlapping widgets (old `canvas.create_rectangle` items sat in the canvas-items layer, below every embedded widget). 4 solid edge frames + 8 handle frames per selection; handle frames bind their own Button-1 / B1-Motion / ButtonRelease-1 so `_on_canvas_click`'s `handle_at` fallback is no longer needed.
- [x] **Object Tree inspector** (`app/ui/object_tree_window.py`) — floating CTkToplevel with a ttk.Treeview showing Name + Type + Layer, two-way selection sync, subscribes to widget_added/removed/reparented/z_changed/selection_changed, unsubscribes cleanly on close.
- [x] **View menu** with `☐ Object Tree` checkbutton + F8 shortcut + two-way state (BooleanVar var flips to False when user closes the window directly).

### Phase 6.3 — Drop-to-reparent ✅

- [x] Added `is_container: bool = False` to `WidgetDescriptor`; flipped to `True` for `CTkFrame`
- [x] `_find_container_at(canvas_x, canvas_y, exclude_id=...)` — DFS walk, returns the **deepest** container whose canvas bbox contains the point; `exclude_id` skips the dragged node + its entire subtree so a widget can't drop into itself
- [x] `_widget_canvas_bbox(widget)` — unified canvas-coord bbox helper via `winfo_rootx/rooty` + `canvas.canvasx/canvasy`
- [x] **Palette drop into container** — `_on_palette_drop` hit-tests the drop point, if a container is found the node is created with `parent_id=container.id` and coords translated to the container's local space
- [x] **Drag existing widget to reparent** — `_maybe_reparent_dragged(event)` on release: computes the widget's coords in the new parent's frame (`winfo_rootx` diff / zoom), writes them to `node.properties`, then calls `project.reparent`
- [x] Dragging a child **outside** its parent's bounds auto-reparents to top-level (same code path — `_find_container_at` returns `None`)
- [x] `_on_widget_reparented` handler destroys the old widget subtree and recreates it under the new master via `_create_widget_subtree` → `_on_widget_added`, since tkinter cannot change a widget's master after creation
- [x] Selection survives reparent (cleared before destroy, redrawn on a short `after`)

### Phase 6.4 — Sibling reorder via drag (tree panel) ✅

- [x] `Project.reparent(widget_id, new_parent_id, index=None)` — added `index` param; clamps + compensates for shift when source/target share a sibling list
- [x] Publishes `widget_z_changed(direction="reorder")` when only the order changed, not a full reparent; workspace already re-lifts siblings in project order on that event
- [x] Object Tree drag detects **3 drop zones** per row via `y / row_height` (top 25% → before, middle 50% → into, bottom 25% → after for containers; 50/50 split for non-containers)
- [x] Tree insertion line — `tk.Frame` overlay placed over the Treeview, shown at row top/bottom edges to signal before/after drops
- [x] Right-click context menu on tree rows (**Rename** / Duplicate / Delete / Bring to Front / Send to Back) — matches the workspace menu exactly; Delete shows a confirmation dialog, Rename reuses `workspace._RenameDialog`
- [x] Tree row label now prefers `node.name` (user-visible name) over descriptor display name, subscribes to `widget_renamed` for live refresh

### Phase 6.5 — Nested code export ✅

- [x] `code_exporter._emit_subtree` walks the tree depth-first, emitting a parent variable before any of its children
- [x] `_emit_widget` takes a `master_var` parameter; top-level widgets pass `master="app"`, nested widgets pass their parent's generated variable name
- [x] `needs_pil` scan switched to `project.iter_all_widgets()` so image detection covers nested trees
- [x] Tested round-trip: `nested_test.ctkproj` → File → Export → the generated `.py` runs and reproduces the builder layout

### Phase 6.6 — Object Tree polish

- [x] **Type filter dropdown** — CTkOptionMenu listing `"All types"` + every widget type actually present in the project (sorted by display name). Rebuilds on every `refresh()` and self-heals to `"All types"` when the last widget of the selected type disappears.
- [x] **Name search entry** next to the dropdown — case-insensitive substring match on `node.name`, combined with the type filter via AND. Ancestors of matches stay visible so the hierarchy is preserved.
- [x] **Search icon button** after the entry (Lucide `search`, tinted `#cccccc`); click focuses the entry.
- [x] **CTkEntry placeholder bug workaround** — CTk 5.2.2's `_activate_placeholder` compares a `StringVar` to `""` (always False), so passing `textvariable=` silently breaks the placeholder. Dropped the textvariable and wired the entry to `self._search_text` via a `<KeyRelease>` binding instead; placeholder now renders at `placeholder_text_color="#888888"` on `fg_color="#2d2d2d"`.
- [x] **Auto-open on launch** — `_object_tree_var` defaults to `True`; `_auto_open_object_tree()` fires 250ms after the startup dialog so the window's `_center_on_parent` sees final geometry.
- [x] **Always above main builder** — `self.transient(parent)` + a short `-topmost` toggle via `_raise_above_parent()` so Windows doesn't stack the main window in front on first launch.
- [x] **Visibility toggle (👁 column)** — real Lucide `eye`/`eye-off` PNGs in the `#0` column, fixed-x via `style.configure(indent=0)` trick, click toggles `WidgetNode.visible`; workspace hides/shows via `canvas.itemconfigure(state="hidden")` for canvas children and fresh `place()`/`place_forget()` for nested children. Builder-only flag — save/load/export unaffected.
- [x] **Lock toggle (🔒 column)** — per-row emoji toggle on `WidgetNode.locked`; workspace `_effective_locked(id)` walks ancestors, blocks drag/resize/arrow-nudge/delete. SelectionController suppresses the 8 resize handles on a locked widget (rectangle still draws so the user sees what's selected).
- [x] **Multi-selection (Object Tree only, Delete only)** — `selectmode="extended"` on the Treeview + `Project.set_multi_selection(ids, primary)`; emits `selection_changed(None)` when `len > 1` so workspace handles + properties panel clear, while the tree keeps its multi-row highlight. Right-click menu on multi-selection shows **only** "Delete N widgets" — duplicate / bring to front / drag-reparent are deliberately disabled for multi (user decision: multi is purely for batch delete).
- [x] **SelectionController rewrite — embedded tk.Frame widgets** for the 4 rectangle edges + 8 resize handles via `canvas.create_window` + `.lift()`. Canvas items sit below any `create_window`-embedded widget, so the old `create_rectangle` approach was hidden by overlapping widgets. Trade-off: lost dashed border pattern.
- [ ] **Workspace: stale drag after slow properties panel load** — clicking a tree row kicks off a heavy properties panel rebuild; motion events queued during the block still carry `B1=held` state, so the workspace widget follows the mouse after release. Partial defense added (`event.state & 0x0100` check in `_on_widget_motion`, `_drag = None` reset on press, `winfo_manager()=="place"` guard in `_apply_zoom_to_widget`). Root cause is properties-panel latency — refactor in progress (see below).

### Phase 6.x — Properties panel rewrite (in progress)

- [ ] Properties panel is heavy enough that clicking a tree row blocks the Tk event loop long enough for queued `<B1-Motion>` events to fire after the physical button release, dragging the workspace widget unintentionally. User is refactoring the panel to cut per-selection rebuild cost. Prototype lives in `tools/ctk_button_treeview_mock.py`. Once the panel is fast, re-test the "widget follows mouse after tree click" bug — if it disappears, keep the defense guards as belt-and-suspenders; if not, dig deeper.

### Phase 6.7 — Layout manager options (later)

- [ ] `layout_type` property on container nodes (`place` default, `pack`, `grid`)
- [ ] "Layout" section in properties panel that reflects the parent's layout type
- [ ] place options (relx, rely, x, y, anchor)
- [ ] pack options (side, anchor, fill, expand, padx, pady)
- [ ] grid options (row, column, rowspan, columnspan, sticky)
- [ ] Visual indicator on workspace (which manager is in use)
- [ ] Code exporter respects `layout_type`

---

## Phase 7 — Polish & Pro Features

- [ ] Multi-selection (Ctrl+click)
- [ ] Marquee selection (drag on empty canvas area)
- [ ] Snap-to-grid (8px grid)
- [ ] Alignment guides (snap to other widgets' edges/centers)
- [ ] Copy / Paste / Cut (Ctrl+C / V / X)
- [ ] Widget tree panel (hierarchical view, parent-child)
- [ ] Z-order management
- [ ] Group / Ungroup widgets
- [ ] Asset manager — copy images into project `assets/` folder for portability
- [ ] **Assets library panel** — user drops fonts/images/icons into a project-scoped library; property dropdowns (e.g., `font_family`, `image`) pull from this library only. No raw system-font selection. Fonts bundled with the exported project for consistent rendering on other machines.

---

## Phase 8 — Advanced (later)

- [ ] Custom user-defined widgets / components
- [ ] Variables panel (StringVar, IntVar, BooleanVar — create + bind)
- [ ] Event handlers (generate command callbacks)
- [ ] Templates / Presets for common windows
- [ ] Project settings (Python version, theme, output structure)
- [ ] Plugin system for new widget types
- [ ] **Gradient button support** — CTk has no native gradient fill for buttons. `background_corner_colors` only tints the tiny padding area outside the rounded shape, not the fill. Three exploration paths to try: (1) PIL-generated gradient image + `CTkButton(image=..., compound="center", fg_color="transparent")` — the export must regenerate the image at runtime for preview = reality; (2) custom `CTkGradientButton` subclass that overrides `_draw()` to paint a PIL gradient on the internal canvas with a rounded-corner mask — ~150–200 lines, fragile across CTk versions; (3) adopt/adapt [tkGradientButton](https://github.com/Neil-Brown/tkGradientButton) (plain tk, canvas color stripes, no rounded corners) — wrong widget family, not CTk-compatible. Pick whichever best preserves `preview = reality` when tried in Phase 8.

---

## Notes / Ideas

> Free space — add anything that doesn't fit a phase yet.

- [x] სურათი ღილაკზე — already supported via Image + Text + Pos (compound)
- ჩარჩოს ფერი — `border_color` property for buttons/frames
- Configurable image size (currently hardcoded 20×20 in `transform_properties`)
- CTk corner_radius limitation note: CTk grows button to `text_w + 2*radius + padding`, so true small circles aren't possible with text — preview = reality, exported code matches
