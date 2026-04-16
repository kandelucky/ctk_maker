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

## Phase 3 — Widget Descriptors (13 / 15 full + 2 partial) ✅

- [x] CTkButton (Phase 0)
- [x] CTkLabel — Geometry + Text (Style/Alignment/Color), transparent bg, justify + wraplength editor
- [x] CTkFrame — Geometry + Rectangle (Corners + Border) + Main Colors
- [x] **Font Decoration** (Underline + Strike) added to CTkButton + CTkLabel via CTkFont(underline, overstrike)
- [x] **CTkCheckBox** — Geometry, Rectangle (+ Border), Checkbox Box Size, Button Interaction (Interactable + Hover + Initially Checked via `apply_state` hook), Main Colors (Fill/Hover/Check Mark), Text + Style subgroup + colors
- [x] **CTkComboBox** — Geometry, Rectangle, Values (multiline → list in `transform_properties`), Initial Value via `apply_state`, Button Interaction, Main + Dropdown Colors, Text + Style + Text Align + colors. `multiline_list_keys = {"values"}` used by the exporter.
- [x] **CTkEntry** — Geometry, Rectangle, Content (Placeholder + Initial Text), Button Interaction, Main Colors (Field Background), Text + Style + placeholder color. `apply_state` delete+insert to push initial text (temporarily flips state to normal for disabled widgets).
- [x] **CTkOptionMenu** — Geometry, Rectangle (no border), Values, Button Interaction, Main + Dropdown Colors, Text + Style + Text Align + colors. `dynamic_resizing=False` hardcoded; builder `text_align` → CTk `anchor` translation in transform.
- [x] **CTkProgressBar** — Geometry, Rectangle + Border, Progress (orientation + `initial_percent` 0–100 int), Main Colors (Track / Progress Fill). `orientation` is init-only → `init_only_keys` + `recreate_triggers`. `on_prop_recreate` hook swaps width/height when orientation flips. `apply_state` converts percent → 0-1 for `widget.set`.
- [x] **CTkRadioButton** — Geometry, Rectangle (+ Border with separate `border_width_unchecked` / `border_width_checked`), Radio Button Box Size, Button Interaction (Interactable + Hover + Initially Checked + **Group**), Main Colors, Text + Style + colors. **Radio group coordination**: radios with the same `group` name share a `tk.StringVar` managed by workspace (`_radio_groups`, `_radio_values`, `_radio_group_counts`). `create_widget` now accepts `init_kwargs` so workspace can inject `{variable, value}` at construction — both are init-only and `configure(value=...)` raises. `recreate_triggers = {"group"}` + workspace `_sync_radio_initial` for live `initially_checked` flips. Standalone radios (empty group) fall back to `widget.select()/.deselect()`; group radios skip `.deselect()` in `apply_state` because it would clobber siblings.
- [~] **CTkScrollableFrame** — partial. Descriptor + schema + registry in place, widget renders and all style/label/scrollbar props work, but nesting children through the builder's `place()` path clashes with CTk's grid/pack-based scrollregion tracking. Unfinished — return to it with the composite-widget integration story (see Phase 6.8 below).
- [x] **CTkSegmentedButton** — schema + descriptor + registry. CTk's `.bind()` raises `NotImplementedError` because it composes multiple inner CTkButtons; workspace `_bind_widget_events` now wraps every bind call in a `_safe_bind` helper that catches `NotImplementedError`, `TclError`, and `ValueError` (the last one because `configure(cursor="fleur")` also rejects unknown kwargs on composite CTk widgets). Events land on the inner buttons via the recursive child loop instead.
- [x] **CTkSlider** — schema + descriptor + registry. `number_of_steps=0` means "continuous" in the builder → `transform_properties` maps 0 to `None`, and the NEW `export_kwarg_overrides` hook mirrors that for the exporter so `CTkSlider(..., number_of_steps=0)` never lands in generated code (it would crash with `ZeroDivisionError` on drag).
- [x] **CTkSwitch** — schema + descriptor + registry. Switch box W/H + `initially_checked` via `apply_state` + `export_state` (`widget.select()`). Button length > 0 gives a pill-shaped knob.
- [~] **CTkTabview** — partial. Descriptor + schema + registry + runtime tab diff (add/delete tabs when `tab_names` changes) + `export_state` emitting `tabview.add("name")` per tab. `is_container=False` for now — **dropping widgets into a specific tab is not yet supported**; the builder only lets you declare tabs + style, and the user must hand-edit the exported file to populate each tab via `tabview.tab("name")` as the master. Revisit with the composite-widget integration story (Phase 6.8) together with CTkScrollableFrame.
- [x] **CTkTextbox** — schema + descriptor + registry. Multi-line text editor; `initial_text` via `apply_state` (`delete("1.0","end")` + `insert("1.0", text)`) + `export_state` mirror. `activate_scrollbars` is init-only on CTkTextbox (configure raises `ValueError`) so it lives in `init_only_keys` + `recreate_triggers`. `button_enabled=False` toggles the widget to `state="disabled"` via `configure`, not `__init__`, because CTkTextbox doesn't take `state` as a kwarg at construction time.
- [ ] Per-widget docs page under `docs/widgets/ctk_*.md` for each new descriptor (help icon already wired)
- [ ] **Perf check**: naive `disabled_when` re-evaluation in properties_panel `_on_property_changed` iterates all props on every change. For 15 widgets × ~5 disabled_when lambdas each, measure drag-time overhead. If noticeable, switch to dep-map approach (`TrackingDict` auto-detects which properties a lambda reads, builds `{trigger_prop: [dependent_props]}` map at rebuild time, so most changes hit O(1) dict lookup instead of O(N) re-evaluation).
- [ ] **Shared descriptor infrastructure** added this session — document once the remaining widgets are done:
  - `init_only_keys` (base class) — schema keys that go to `__init__` but never to `configure`
  - `recreate_triggers` — props whose change causes the workspace to destroy + recreate the widget
  - `on_prop_recreate(prop_name, properties)` — optional hook to commit derived overrides before recreation (e.g. ProgressBar width↔height swap)
  - `apply_state(widget, properties)` — runtime state that can't go through kwargs (`.select()`, `.set()`, `delete+insert`)
  - `export_state(var_name, properties)` — exporter-side counterpart: list of post-construction lines the exporter should emit (`.select()`, `.set(val)`, `.insert(0, text)`, `.add("tab")`…) so the exported `.py` reaches the same visual state as the builder preview. Needed because the exporter can't call `apply_state` directly (it works with source code, not live widgets).
  - `export_kwarg_overrides(properties)` — exporter-side per-key replacements, used when a raw property value can't go straight into generated code (CTkSlider's `number_of_steps=0 → None` is the first user).
  - `create_widget(master, properties, init_kwargs=None)` — workspace-injected constructor kwargs for cross-widget coordination (currently radio group `{variable, value}`)
  - `canvas_anchor(widget)` — composite widgets return their outer container for canvas embedding / event binding / selection bbox. Workspace keeps a parallel `_anchor_views` dict and passes it to `SelectionController`.
  - `_safe_bind` in workspace `_bind_widget_events` — catches `NotImplementedError`/`TclError`/`ValueError` around both `.bind(...)` and `widget.configure(cursor=...)` so CTk composite widgets (CTkSegmentedButton, CTkScrollableFrame) that override `.bind` or reject unknown configure kwargs don't blow up widget creation. Events land on the inner children via the recursive bind loop instead.
  - New enum `ptype`: **"orientation"** → `["horizontal", "vertical"]`, added to `format_utils.enum_options_for` and the editor registry.

- [ ] **CTkTabview: drop widgets into specific tabs (container nesting)** — deferred from Phase 3 when we built the descriptor. Today the builder only lets you configure the tab bar itself (tab names, colors, size, border) and the exporter emits a naked `tabview.add("name")` per tab. To actually populate a tab you hand-edit the exported `.py` and use `tabview.tab("name")` as the master of each child widget.

  **What's missing in the builder:**
  - The "active tab" context — when the user has a CTkTabview selected and drags a widget from the palette onto it, the builder has to know which tab the drop should land in. Cleanest: whatever tab is currently visible (`tabview.get()`) becomes the parent, same as how ScrollableFrame would work once that lands.
  - Per-child "parent tab" storage in `WidgetNode` — child already has `parent_id`; we need an additional `parent_slot` (string, tab name) that stays stable across saves/loads and reparents.
  - Runtime rendering in the workspace: `_on_widget_added` for a child whose parent is a CTkTabview must use `tabview.tab(node.parent_slot)` as the master instead of the tabview itself. Same for reparent and when the active tab changes.
  - `is_container = True` flip once the above lands. Until then CTkTabview stays `False` so palette drops don't silently go to the canvas root.
  - Exporter: two-pass (assign var names first, then emit) so `child = CTkLabel(tabview_1.tab("Tab 1"), …)` can reference the parent's var. The `parent_slot` gets inlined as the `.tab("...")` call.
  - Tab name edit propagation: if the user renames `Tab 1` → `Main`, every child with `parent_slot == "Tab 1"` must migrate to `"Main"`. Currently the tab diff in `apply_state` treats renames as a delete + add, which would orphan children. Needs a proper rename path with old→new name tracking.

  **Same story applies to CTkScrollableFrame** (Phase 6.8 composite-widget integration) — the two widgets share enough that the solution should be designed once and applied to both.

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

## Phase 2.11 — Refactor round 2 + architecture dashboard ✅

- [x] **ZoomController extraction** (`app/ui/zoom_controller.py`, 270 lines) — owns zoom value, `logical↔canvas` coordinate helpers, `apply_to_widget`, scaled font building, and the bottom status-bar `[−] [+] [1:1] [menu ▼]` widgets. Workspace wires an `on_zoom_changed` callback that redraws the document rect + grid + selection chrome. Added a **1:1 reset button** between `+` and the percentage menu — one click back to 100%. `Ctrl+MouseWheel` binding moved to `_bind_widget_events` so it works on workspace widgets too, not only on empty canvas.
- [x] `workspace.py` shrunk **1232 → 1006 lines** (-226) after the ZoomController extraction + `_dbg` logging cleanup (defense guards `event.state & 0x0100` and `winfo_manager() == "place"` kept as belt-and-suspenders).
- [x] **`_RenameDialog` extraction** — moved from `workspace.py` into `app/ui/dialogs.py` as public `RenameDialog`. Object Tree now imports the public symbol from `dialogs.py` instead of leaking a `_`-prefixed name across modules.
- [x] **Properties panel v2 package split** (`app/ui/properties_panel_v2/`) — 1445-line prototype turned into a real package: pure pieces (`constants.py`, `format_utils.py`, `type_icons.py`) live next to the panel; per-type UI lives under `editors/` (base / color / boolean / number / multiline / image / enum); `OverlayRegistry` keyed by `(iid, slot)` replaces the 6 per-type dicts + 5 placement methods the prototype carried. `panel.py` shrunk **1445 → 1003 lines**. Behaviour unchanged — mechanical extract only.
- [x] **Object Tree performance overhaul** — generic `_on_project_changed` split into granular handlers so cosmetic events (`widget_renamed`, `widget_visibility_changed`, `widget_locked_changed`) update a single cell or subtree tag cascade instead of deleting + reinserting every row. Structural events (add / remove / reparent / z_changed) still fall back to full refresh. Dead `property_changed` subscription removed.
- [x] **Search debounce** in Object Tree — 200ms `after_cancel` pattern on the name search entry so typing a 10-character query triggers one refresh at the end of the burst, not one per keystroke. Cancelled cleanly on window close.
- [x] **Ctrl+C / Ctrl+V in Object Tree** — `Project.clipboard: list[dict]`, `copy_to_clipboard(ids)` (filters out descendants whose ancestor is also selected so containers cover their children), `paste_from_clipboard(parent_id)` (fresh UUIDs via `_clone_with_fresh_ids`, +20/+20 offset, auto-selects the pasted widgets). Paste target rules: container selection → inside it, leaf selection → sibling, nothing selected → top level. **Non-Latin layout fallback**: `<<Copy>>` / `<<Paste>>` virtual events bound on the Toplevel so main_window's `bind_all("<Control-KeyPress>")` keycode router reaches our handlers on Georgian / Russian keyboards.
- [x] **Architecture dashboard** — `tools/gen_architecture_dashboard.py` walks `app/` with AST, extracts LOC + docstring + top-level classes/functions + internal imports, emits `docs/architecture_dashboard.html` as a single self-contained vis.js interactive network. Nodes are sized by LOC, coloured by package (core / io / widgets / ui), hover tooltip shows the one-line description, click opens a right panel with full metadata + imports / imported-by lists + three action buttons: **📋 Copy context** (markdown snippet for pasting into chat), **💾 Copy path**, **✏️ Open in VSCode** via `vscode://file/` protocol.
- [x] **Georgian module descriptions** — `docs/module_descriptions.ka.json` (one-line human-language explanation per module, 38/39 coverage). Dashboard loads the sidecar at generation time and renders the Georgian text in an accent-coloured block inside the details panel; copy-context snippet uses the Georgian text when available. Scripts stay clean — descriptions live entirely in the JSON sidecar.
- [x] **Architecture reference docs** — `docs/ARCHITECTURE.md` (layered index of every source file with one-line purpose, grouped by `core` / `io` / `widgets` / `ui`; event-bus traffic table showing who publishes and who listens) + `tools/gen_architecture_graph.py` (falls back to `.dot` output without requiring the `dot` binary — paste into https://dreampuf.github.io/GraphvizOnline/).
- [x] **`.gitignore` updates** — added `docs/architecture_dashboard.html`, `docs/architecture_graph.dot`, `docs/architecture_graph.svg`, `tools/_test_alpha.png` so auto-generated artifacts stay out of git.

---

## Phase 2.12 — Properties panel UX polish + docs (2026-04-14) ✅

- [x] **DragScrubController extraction** (`app/ui/properties_panel_v2/drag_scrub.py`) — Photoshop/Figma-style horizontal drag on numeric row labels. `<ButtonPress-1>` on column `#0` of a number row starts a scrub; `<B1-Motion>` commits `±1` per pixel accumulated in a float buffer; `<ButtonRelease-1>` cleans up; `<Motion>` flips the cursor to `sb_h_double_arrow` when hovering a valid target. Alt-hold = 0.2× fine scrub. `min` / `max` schema lambdas re-evaluated against the live props dict so clamps respect `disabled_when`-style dependencies.
- [x] **Pair row labels fix** — `_insert_prop` in `panel.py` was using `prop["row_label"]` for every child of a numeric pair, so the first item (X / W) showed up as "Position" / "Size" under the virtual parent. Now paired props always fall back to `prop["label"]`, so children read "X / Y" and "W / H" correctly.
- [x] **Selection focus release** — clicking empty tree area clears the tree's visual selection *and* the internal `focus("")` active item *and* hands keyboard focus back to `winfo_toplevel()`. `_on_selection` from the event bus also releases focus after a workspace-driven selection, so arrow keys nudge the widget in the canvas instead of re-activating the tree cursor.
- [x] **Corner Radius flatten** — removed the single-child "Corners" subgroup from `CTkFrame` and `CTkButton`; `corner_radius` now renders as a flat row under "Rectangle" with `row_label` "Corner Radius". The subgroup preview (showing the value next to the header while collapsed) was the root of user confusion — single-child subgroups are officially banned from the schema convention.
- [x] **Image & Alignment cleanup** (CTkButton) — flattened the misleading "Alignment" subgroup that only wrapped the Size pair; renamed `row_label`s to user-friendly names (`Size` → `Icon Size`, `Position` → `Icon Side`, `Normal Image Color` → `Normal Color`, `Disabled Image Color` → `Disabled Color`); replaced the `open` / `clear` text buttons on the Image row with compact `⋯` / `✕` icon labels (100 → 50 px reserve, filename label gets the extra width).
- [x] **Style preview initials** — `STYLE_BOOL_NAMES` switched from full words (`Bold / Italic / ...`) to single letters (`B I U S`) so the subgroup preview fits within the value cell at any reasonable panel width. Active bool = bright (`#cccccc`), inactive = dim (`BOOL_OFF_FG`).
- [x] **CTkLabel Wrap subgroup** — `font_wrap` moved from the Style subgroup into a new "Wrap" subgroup together with `wraplength`; `Enabled` + `Length` rows, length is `disabled_when` Enabled is off. Leaves the Style subgroup pure (Bold / Italic / Underline / Strike only).
- [x] **`justify` → "Line Align"** — renamed in CTkLabel schema so the user-facing label isn't a raw Tk term. Explicitly distinct from `anchor` which is the text-block placement.
- [x] **CTkButton `font_wrap` removed** — the flag was never wired to any real CTk kwarg (CTkButton doesn't accept `wraplength` or equivalent). Removed from `default_properties`, `property_schema`, and `_FONT_KEYS`.
- [x] **`bg_color="transparent"` attempt (reverted)** — tried syncing `widget.configure(bg_color=<effective parent bg>)` after every create/reconfigure plus walking up the parent chain to resolve transparent ancestors. Did not fix the black-corner artifact on rounded widgets sitting directly on `tk.Canvas`. Root cause is in CTk itself (`_detect_color_of_master` can't read a canvas background). User decided to accept the visual artifact rather than keep patching. All workspace and schema changes reverted.
- [x] **Help button → wiki URL** — `_open_widget_docs` was pointing at `github.com/.../blob/main/docs/widgets/{slug}.md`; switched to `github.com/.../wiki/{TypeName}` so the `?` icon lands on the rendered wiki page directly.
- [x] **CTkLabel docs (repo + wiki)** — `docs/widgets/ctk_label.md` + `ctk_visual_builder.wiki/CTkLabel.md` with matching tables (Geometry / Text → Size / Style / Alignment / Wrap / Color). Wiki sidebar + catalog status bumped to ✅. `label.png` screenshot added to wiki `images/`.
- [x] **CTkButton docs refresh** — existing `ctk_button.md` (repo + wiki) was stale from before the Corner Radius flatten, Button Interaction rename, Icon Size / Icon Side rename, and Normal/Disabled Color shortening. Both files rewritten to match the current schema; new wiki `button.png` screenshot committed.
- [x] **`canvas-workspace.md` user guide** — the `docs/user-guide/canvas-workspace.md` file was a TODO-list stub; filled in with Layout / Tools / Placing / Selecting / Moving / Resizing / Delete+Rename / Zoom+Pan / Tips sections using compact tables (no ASCII diagrams, no dev internals per the concise-docs rule).

---

## Phase 2.13 — Object Tree dock + Image widget (2026-04-15) ✅

- [x] **ObjectTreeWindow split** — the old `ObjectTreeWindow(CTkToplevel)` was a single ~1200-line class that only existed as a floating inspector. Refactored into two:
  - **`ObjectTreePanel(ctk.CTkFrame)`** — all the tree-building, filter row, event-bus subscriptions, drag-to-reparent, right-click menu, rename/copy/paste/delete/z-order handlers — everything non-Toplevel now lives in a plain Frame so the main window can embed it into a sidebar.
  - **`ObjectTreeWindow(ctk.CTkToplevel)`** — ~90-line wrapper that creates a Toplevel (title / geometry / transient / protocol / `_center_on_parent` / `_raise_above_parent`) and puts a `ObjectTreePanel` inside. Kept for the floating "pop-out" inspector that users can still toggle via the View menu.
- [x] **Docked in the main window right sidebar** — `main_window.py` now wraps the Properties panel in a **nested vertical `tk.PanedWindow`** with the docked `ObjectTreePanel` above it. Drag the horizontal sash (7px, `#3a3a3a`) to resize either region. Initial heights: 280 / stretch.
- [x] **Startup no longer auto-opens the floating Object Tree** — `_auto_open_object_tree` removed, `_object_tree_var` defaults to `False`. The docked panel is always visible; the View menu's "Object Tree" checkbutton now only toggles the additional floating window for users who want a detachable view.
- [x] **Scrollbar overflow** — the docked tree originally wouldn't scroll because `ttk.Treeview` inside a default `pack_propagate(True)` chain was expanding its parent frames past the PanedWindow's assigned pane height. Fix: `pack_propagate(False)` on the Panel frame + inner container + `tree_row` frame, so the PanedWindow sash size wins over the tree's content request.
- [x] **Scrollbar pack order fix** — scrollbar was invisible because `self.tree.pack(side="left", fill="both", expand=True)` was called BEFORE `vscroll.pack(side="right", fill="y")`. Tk's pack geometry manager gave the tree's `expand=True` ALL the horizontal space first, leaving zero for the scrollbar. Flipped the order so the scrollbar packs first.
- [x] **Scrollbar styling** — `tk.Scrollbar` on Windows ignores colour kwargs in favour of the OS theme, so it rendered as white. Switched to a `ttk.Scrollbar` with a custom `ObjectTree.Vertical.TScrollbar` style (`background=#3a3a3a`, `troughcolor=#1a1a1a`, `arrowcolor=#888888`, pressed/active maps) to match the dark dark-theme look.
- [x] **Row density** — dropped tree row height from 30 → 22 and font size from 11 → 10 so the compact docked pane fits more widgets.
- [x] **Copy / paste focus fix** — after the refactor Ctrl+C / Ctrl+V only worked once because the bindings lived on the old Toplevel; in the docked Frame they had to move onto `self.tree` directly (widget-level). Handlers also call `self.tree.focus_set()` at the end so subsequent shortcuts keep routing to the tree after a paste rebuilds the rows.
- [x] **Image widget descriptor** — new `app/widgets/image.py` + palette entry (`Display › Image`). Builder-only composite: CTk doesn't ship a pure image widget, so it wraps `CTkLabel(text="", image=CTkImage(...))`. Schema: Geometry, Image (file + preserve_aspect), Tint (normal / disabled colour overlay), Background. Placeholder fg_color = `#444444` when no image is set so the widget is still visible in the canvas.
- [x] **`ctk_class_name` base-class hook** — new descriptor attribute the exporter uses when emitting the constructor call. Defaults to `type_name`, but builder-only composite widgets override (Image → `CTkLabel`) so the generated code stays on CTk's public API.
- [x] **`_image_source` exporter fallback** — CTkButton keeps the icon size in `image_width/height`, but the pure Image widget uses the row's own `width/height`. The exporter now falls back to `width/height` when the icon-specific keys are absent.
- [x] **CTkLabel warning silenced** — `self._type_icon_label.configure(image="")` on deselect was passing an empty string (not `None`), which tripped CTkLabel's "Given image is not CTkImage but <class 'str'>" warning at startup. Replaced both call sites with `configure(image=None)`.

---

## Phase 6.3 — Layout managers split + icons (2026-04-16) 🚧

Preparatory refactor before the real WYSIWYG arranger (stage 3). The tk
`pack` geometry manager is split into two distinct layout types, matching
Qt Designer's 20-year-old UX: `Vertical Layout` (QVBoxLayout, tk
`side=top`) and `Horizontal Layout` (QHBoxLayout, tk `side=left`). The
generic `pack` was ergonomically ambiguous — 95% of real layouts pick one
direction and stick with it; the per-child `pack_side` row just created
confusion.

### Data model
- [ ] `layout_type` ∈ `place / pack / grid` → `place / vbox / hbox / grid`.
- [ ] Child widgets drop the `pack_side` property entirely — direction comes
  from the parent's type. `pack_fill`, `pack_expand`, `pack_padx`,
  `pack_pady` stay on the child.
- [ ] Load migration for v0.0.10 `.ctkproj` files: `layout_type == "pack"`
  → `vbox` (the pack default was `side=top`, so vertical is the safe
  fallback).

### Code exporter
- [ ] `vbox` → `.pack(side="top", …)`, `hbox` → `.pack(side="left", …)`.
- [ ] `pack_side` per-child is no longer read.

### Icons (Lucide)
- [ ] `place` → `crosshair`
- [ ] `vbox` → `rows-3` (≡ horizontal bars stacked vertically — matches Qt)
- [ ] `hbox` → `columns-3` (⋮⋮⋮ vertical bars side by side — matches Qt)
- [ ] `grid` → `grid-3x3`

### Surface area
- [ ] Properties panel enum popup shows icon + display name per option
  (`Absolute` / `Vertical` / `Horizontal` / `Grid`). `tk.Menu` supports
  `image=` on `add_command` — no custom popup needed.
- [ ] Canvas chrome title suffix (` · pack` → ` · vertical` / ` · horizontal`).
- [ ] Canvas container badges (`[pack]` → `[vbox]` / `[hbox]`).
- [ ] Object Tree suffix likewise.

Canvas drag/drop stays absolute — the real WYSIWYG pack/grid arranger is
still deferred to stage 3.

---

## Phase 6 — Layout managers, stage 1 + 2 (2026-04-16) ✅

Tk's three geometry managers (`place` / `pack` / `grid`) modelled as a per-container property. Canvas editing stays absolute; only the exported `.py` file changes shape.

### Stage 1 — data model + export
- [x] **Shared schema module** (`app/widgets/layout_schema.py`) — `LAYOUT_TYPE_ROW`, `LAYOUT_DEFAULTS`, `LAYOUT_NODE_ONLY_KEYS`, `child_layout_schema(parent_layout_type)`. Defines `pack_*` / `grid_*` rows once so every descriptor pulls from the same source.
- [x] **Containers carry `layout_type`** — `CTkFrameDescriptor`, `CTkScrollableFrameDescriptor`, `WindowDescriptor`, `Document.DEFAULT_WINDOW_PROPERTIES` all default to `place` (backwards-compatible).
- [x] **Properties panel injects child layout rows dynamically** — `_layout_extras` cache + `_effective_schema(descriptor)` helper. Six existing `descriptor.property_schema` access sites switched to use the helper so disabled_when, pair detection, popup menus all see the parent-driven rows. Layout key defaults backfilled on first open.
- [x] **New enum types** (`layout_type`, `pack_side`, `pack_fill`, `grid_sticky`) wired through `format_utils.enum_options_for` + `editors/__init__._EDITORS`.
- [x] **Workspace strips layout keys** before passing properties to CTk — `_strip_layout_keys()` shared by the create-widget path and the live-configure path. Otherwise `pack_side="top"` would land in `CTkButton.__init__`.
- [x] **Code exporter emits the right call per parent** — new `_geometry_call(full_name, props, parent_layout)` returns `.place(x=, y=)` / `.pack(side=, fill=, …)` / `.grid(row=, column=, sticky=, …)`. Default values are omitted from the generated kwargs to keep the output lean.

### Stage 2 — visual feedback
- [x] **Chrome title suffix** — Window's `layout_type ≠ place` → `· pack` / `· grid` appended to the document name strip.
- [x] **Container badge on canvas** — `[pack]` / `[grid]` rendered in italic dim grey at every Frame's top-right corner when manager isn't default. Invisible for `place` containers so plain forms read the same as before.
- [x] **Dashed grid-cell overlays** — for any container with `layout_type == "grid"`, faint dashed lines at proportional row/column positions derived from children's `grid_row` / `grid_column` values. Uses the document rect for root-level grids and the Frame's bbox for nested grids.
- [x] **Object Tree marks containers** — name suffix `[pack]` / `[grid]` added to container rows; subscribed to `property_changed("layout_type")` so the row updates in place without a full tree rebuild.
- [x] **Property triggers** — `LAYOUT_OVERLAY_TRIGGERS = {layout_type, grid_row, grid_column, grid_rowspan, grid_columnspan}` repaints overlays on the canvas without recreating widgets.

### Stage 3 — true WYSIWYG (deferred)
- [ ] Pack/grid containers arrange children automatically on canvas using the real geometry managers.
- [ ] Drag in a non-place container reorders rather than repositioning pixels.
- [ ] Resize handles + selection bbox react to manager (pack/grid hide manual resize, fall back to manager-driven sizing).

---

## Phase 2.14 — Panel visual unification (2026-04-16) ✅

- [x] **Object Tree panel header matches Properties** — added a centered `Segoe UI 13 bold` title label at the top (`"Object Tree"`) and moved the document-status stripe from the bottom of the tree container to directly beneath the title, mirroring Properties' `title → type-header-stripe → body` structure. Both docked panels now read as parallel UI elements instead of one feeling like a stripped-down floating inspector.
- [x] **Widget Box header matches Properties / Object Tree** — title restyled from `Segoe UI 11 bold, anchor="w", pady=(10,6)` to `Segoe UI 13 bold, centered, pady=(6,2)` so all three sidebar panels share the exact same title style.
- [x] **Object Tree scrollbar switched ttk → CTkScrollbar** — the Phase 2.13 `ttk.Scrollbar` still carried Windows-style arrow buttons (▲▼) at each end. Now uses `CTkScrollbar` with the same kwargs as Properties (`width=10, corner_radius=4`) so every panel's scroll thumb is the identical thin modern pill. The old `_build_style` ttk Scrollbar map entries are left in place — harmless, and the Treeview still uses that ttk style block for its row/heading colours.
- [x] **Widget Box CTkScrollableFrame scrollbar styled to match** — `CTkScrollableFrame` only exposes the scrollbar colour kwargs (`scrollbar_fg_color / scrollbar_button_color / scrollbar_button_hover_color`), not width, so we reach into `self.scroll._scrollbar.configure(width=10, corner_radius=4)` after construction. Not ideal to touch a private attribute, but customtkinter exposes no public API for it and the attribute has been stable across releases.
- [x] **All scrollbars → transparent trough** — after comparing Current / NoTrough-w10 / Thin-w8 / Thinner-w6 / Minimal-w4 variants in `Desktop/Test/scrollbar_test.py`, settled on keeping width=10 for usable click targets but dropping the `#1a1a1a` trough background. Every scrollbar (Object Tree, Properties, Workspace h+v, Widget Box) now uses `fg_color="transparent"`, so only the `#3a3a3a` thumb pill is visible — the "flat" modern look with no dark channel reserving column space.
- [x] **Scrollbar lab script kept** — `Desktop/Test/scrollbar_test.py` stays as a side-by-side comparison harness for future scrollbar tweaks. Five ScrollableFrame columns, one per variant, same content, instant A/B review.

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

## Phase 5 — Window Settings ✅ (partial — v0.0.8)

- [x] Virtual `WINDOW_ID` node + `WindowDescriptor` property schema
- [x] Properties panel routes the virtual Window selection through `Project.update_property(WINDOW_ID, …)`
- [x] Canvas title-bar chrome (title, settings icon, minimize placeholder, close button)
- [x] Title-bar drag-to-pan (works regardless of active tool)
- [x] Dirty indicator `*` next to the project name on the chrome
- [x] Close button → `request_close_project` event → MainWindow close flow
- [x] Width / height bound to `document_width` / `document_height` (single source of truth)
- [x] `fg_color`, `resizable_x`, `resizable_y`, `frameless`
- [x] Unified `project.name` as the window title — no separate rename field, only New / Save As
- [x] Exporter emits `app.title(project.name)` + resizable / frameless / fg_color
- [ ] `appearance_mode` (system / light / dark) — kept at the global Settings menu for now
- [ ] Window icon (`iconbitmap` / `iconphoto`) — Phase 8

---

## Phase 5.5 — Multi-document canvas ✅

> One `.ctkproj` holds a main window + any number of dialogs, all visible on the
> same canvas and editable side by side. Qt Designer-style MDI inside a single
> project.

### Model ✅
- [x] `Document` dataclass: `id`, `name`, `width`, `height`, `canvas_x`, `canvas_y`, `window_properties`, `is_toplevel`, `root_widgets`
- [x] `Project` holds `documents: list[Document]` + `active_document_id`
- [x] Accessors: `project.active_document`, `project.get_document(id)`, `project.set_active_document(id)`, `project.find_document_for_widget(id)`
- [x] Migration layer: legacy `project.root_widgets` / `document_width` / `window_properties` are `@property` shims that read/write through the active document so existing call sites keep working untouched
- [x] `iter_all_widgets` walks every document's tree so cross-doc lookups resolve

### Persistence ✅
- [x] `project_saver` writes v2 format with a `documents[]` array (+ active id)
- [x] `project_loader` reads v1 single-document files and auto-upgrades them into a one-entry `documents` list
- [x] `clear()` resets to a single fresh `Main Window` document and fires `active_document_changed`

### Canvas rendering ✅
- [x] Workspace iterates `project.documents` in render order (active last) and draws each one's rect + grid + chrome + raised widgets as a stacked block so overlapping forms compose correctly
- [x] Shared zoom applies uniformly to every document via `logical_to_canvas(lx, ly, document=...)`
- [x] Chrome drag moves the clicked document's `canvas_x / canvas_y`; canvas-level `<B1-Motion>` fallback catches motion when the cursor slips off the chrome mid-drag
- [x] Hand-tool pan is unchanged — it still drags the whole viewport
- [x] Active document's chrome is full-bright, inactive docs render dimmer (`#222222` bg + grey fg)
- [x] Document coordinate system: widget `x / y` is document-relative; `logical_to_canvas` adds each doc's offset at paint time

### Palette + drag ✅
- [x] Palette drop picks the document under the cursor via `_find_document_at_canvas` and adds the new widget to that doc's tree
- [x] Dragging a top-level widget from Document A to Document B detects the cross-doc case in `_maybe_reparent_dragged`, moves the node between root lists, and replays the `widget_reparented` event so the workspace rebuilds the subtree under the new root
- [x] Drop outside any document falls back to the currently active document

### Inspectors ✅
- [x] Object Tree shows only the active document's widget tree
- [x] Doc header strip pinned to the BOTTOM of the Object Tree window shows which form is being edited (icon + name + `(Dialog)` suffix for toplevels); click = open Window settings
- [x] 6-space indent per depth level so nested widgets visually step away from their parent
- [x] `app-window` icon picked for the Window header (distinct from `layout-panel-top` used by CTkTabview)
- [x] Selection routing ignores synthetic `doc:*` iids so multi-select only tracks real widgets
- [x] Properties panel Window selection routes through `_WindowProxy`, which always resolves to the active document and exposes every `DEFAULT_WINDOW_PROPERTIES` key (fg_color, resizable_x/y, frameless, grid_style/color/spacing)

### Lifecycle ✅
- [x] Menu `Form → Add Dialog` / `Form → Remove Current Document`
- [x] Workspace top toolbar `+ Add Dialog` button (mirrors the menu)
- [x] `AddDialogSizeDialog` — name + size preset picker (Same as Main / Alert / Compact / Medium / Settings / Wizard / Custom), seeds defaults from the main window
- [x] Chrome close `✕` on a Dialog removes that document (with confirm); on the Main Window it runs the project-close flow — you can't accidentally delete the root form
- [x] Default new project has a single `Main Window` document (`is_toplevel=False`); the first document is protected from rename-less removal via menu + chrome
- [x] Rename for dialogs happens through the Properties panel's name entry (inline); main window name stays tied to `project.name` (New / Save As only)

### Undo / redo ✅
- [x] `AddDocumentCommand`, `DeleteDocumentCommand`, `MoveDocumentCommand` (press→release coalesced for title-bar drag)
- [x] Widget commands key off the widget `id` unchanged; `find_document_for_widget` + widget-level reparent events keep cross-doc drags undoable
- [x] Undo after `Remove Dialog` restores the document + every widget at its original index

### Code exporter ✅
- [x] Emits one `.py` with one class per document:
  - First document (`is_toplevel=False`) → `class MainWindow(ctk.CTk):`
  - Dialogs → `class LoginDialog(ctk.CTkToplevel):` etc.
- [x] Each class has a clean `__init__` (title / geometry / resizable / frameless / fg_color) that calls `self._build_ui()` for widget construction
- [x] `if __name__ == "__main__":` wires `ctk.set_appearance_mode(...)` + the main class + `mainloop()` and leaves commented instructions for opening each dialog (`# dialog = LoginDialog(app)`)
- [x] Per-class variable names stay attributes (`self.button_1 = …`) so event handlers added later can reach them

### Window Properties polish ✅
- [x] `fg_color` live preview — document rectangle recolours on change
- [x] `Builder Grid` group in the Window schema: Style (none / dots / lines), Colour, Spacing (4–200)
- [x] Grid is builder-only metadata, never emitted in exported code
- [x] Grid bleed fixed: overlapping docs no longer show each other's grid through their rectangle (per-doc stacked draw order)

### Test plan ✅
- [x] Create Main Window + Dialog in one project, add widgets to each
- [x] Export → one `.py` with both classes, runs cleanly
- [x] Save / close / reopen — active doc + positions + sizes + grid settings persist
- [x] Chrome drag, cross-doc widget drag, undo/redo of document lifecycle all survive the round trip

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
- [~] **Workspace: stale drag after slow properties panel load** — defense guards in place (`event.state & 0x0100` check in `_on_widget_motion`, `_drag = None` reset on press, `winfo_manager() == "place"` guard in `ZoomController.apply_to_widget`). Properties panel v2 package split is done (see Phase 2.11), so root-cause retest is pending — if the stale drag no longer reproduces, the guards stay as belt-and-suspenders.

### Phase 6.x — Properties panel rewrite

- [x] **Package structure** — prototype in `tools/ctk_button_treeview_mock.py` has graduated to a real `app/ui/properties_panel_v2/` package (see Phase 2.11 for the A/B/C split: package extract, editor registry, overlay registry).
- [ ] **Retest stale drag** — with the faster panel, re-verify whether "widget follows mouse after tree click" still reproduces. If gone, close the Phase 6.6 guard-only entry; if not, dig deeper into where motion events are queueing up.

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

- [ ] Multi-selection (Ctrl+click) — Object Tree already supports it via `selectmode="extended"`; workspace canvas still single-select only
- [ ] Marquee selection (drag on empty canvas area)
- [ ] Snap-to-grid (8px grid)
- [ ] Alignment guides (snap to other widgets' edges/centers)
- [~] **Copy / Paste / Cut (Ctrl+C / V / X)** — Ctrl+C / Ctrl+V implemented in Object Tree (multi-select aware, container-as-target, non-Latin layout fallback via `<<Copy>>` / `<<Paste>>` virtual events). Still pending: workspace canvas bindings, Cut (Ctrl+X), OS-level clipboard integration so snippets survive across app restarts or cross-project paste.
- [ ] Widget tree panel (hierarchical view, parent-child) — already exists (`app/ui/object_tree_window.py`), this legacy entry predates it
- [ ] Z-order management
- [ ] Group / Ungroup widgets
- [ ] Asset manager — copy images into project `assets/` folder for portability
- [ ] **Assets library panel** — user drops fonts/images/icons into a project-scoped library; property dropdowns (e.g., `font_family`, `image`) pull from this library only. No raw system-font selection. Fonts bundled with the exported project for consistent rendering on other machines.

---

## Phase 7.5 — Python import (`.py` → editable project)

> Reverse of `code_exporter` — take an existing CustomTkinter `.py`
> file and rebuild a `.ctkproj` so the user can open it in the
> builder, rearrange visually, then re-export. Three realistic tiers,
> ordered by effort:

### Tier 1 — round-trip our own exports (easy)
- [ ] AST parser that only recognises files emitted by
      `code_exporter.generate_code`: predictable shape, every widget
      has a `ctk.CTkXxx(master, kwargs...)` call followed by a
      `var.place(x=, y=)` line, all kwargs are literal (strings, ints,
      bools, list literals, `ctk.CTkFont(...)`, `ctk.CTkImage(...)`).
- [ ] Resolve kwargs back to `node.properties`, reverse the exporter's
      `_NODE_ONLY_KEYS` + `init_only_keys` + `multiline_list_keys`
      conventions (e.g. `values=['a','b']` → newline-separated string
      again).
- [ ] Reconstruct the nesting tree from the `master=` parameter chain.
- [ ] File → Open Python... menu entry that accepts `.py` files emitted
      by the builder. Clear error dialog when a file doesn't match the
      expected shape.
- [ ] Round-trip test: export a project → delete `.ctkproj` → open the
      `.py` → project reproduced exactly.

### Tier 2 — arbitrary `.place()`-based CTk code (medium, depends on Tier 1)
- [ ] Handle constructor variables that point at helper values earlier
      in the file (`self.logo = CTkImage(...)` + `CTkButton(image=self.logo)`).
- [ ] Recognise `class App(ctk.CTk)` patterns — walk the `__init__`
      body, treat `self.<name> = ctk.CTkXxx(...)` as top-level widgets,
      parent-resolve via the first positional arg.
- [ ] Drop / warn on things we cannot represent yet: `command=` callbacks,
      lambdas, loops, conditionals, `.bind(...)` calls — log them in
      the import report dialog so the user knows what was skipped.
- [ ] `font=ctk.CTkFont(...)` and `image=ctk.CTkImage(...)` nested calls
      → re-extract into our `font_size` / `font_bold` / `image` properties.

### Tier 3 — grid / pack layouts (hard, depends on Phase 6.7)
- [ ] Requires Phase 6.7 (layout managers) shipped first — there is no
      point parsing `.grid(row=0, column=1, sticky="nsew")` if our
      model can't express it.
- [ ] Once layout managers exist: read `.grid()` / `.pack()` calls
      alongside `.place()`, store the options on the node, and teach
      the exporter to round-trip them.
- [ ] Open CTk's own `examples/complex_example.py` and
      `examples/image_example.py` as a success criterion — both use
      `grid` heavily.

### Alternative / complement — side-by-side reference viewer (no import)
- [ ] "Open in VSCode" button on the CTk reference entries (we already
      have this pattern in `docs/architecture_dashboard.html`) so the
      user can read the real `.py` next to the builder without import.

---

## Phase 8 — Advanced (later)

- [ ] Custom user-defined widgets / components
- [ ] Variables panel (StringVar, IntVar, BooleanVar — create + bind)
- [ ] Event handlers (generate command callbacks)
- [ ] Templates / Presets for common windows
- [ ] Project settings (Python version, theme, output structure)
- [ ] Plugin system for new widget types
- [ ] **Gradient button support** — CTk has no native gradient fill for buttons. `background_corner_colors` only tints the tiny padding area outside the rounded shape, not the fill. Three exploration paths to try: (1) PIL-generated gradient image + `CTkButton(image=..., compound="center", fg_color="transparent")` — the export must regenerate the image at runtime for preview = reality; (2) custom `CTkGradientButton` subclass that overrides `_draw()` to paint a PIL gradient on the internal canvas with a rounded-corner mask — ~150–200 lines, fragile across CTk versions; (3) adopt/adapt [tkGradientButton](https://github.com/Neil-Brown/tkGradientButton) (plain tk, canvas color stripes, no rounded corners) — wrong widget family, not CTk-compatible. Pick whichever best preserves `preview = reality` when tried in Phase 8.

- [ ] **Widget-to-widget value binding ("Command Target")** — CTkSlider, CTkSwitch, CTkSegmentedButton, CTkCheckBox, CTkRadioButton, CTkComboBox, CTkOptionMenu, and CTkEntry all accept a `command=callable` callback that fires when the user changes the widget's value. CTk's official `reference/ctk_official/manual_tests/test_vertical_widgets.py` demonstrates the simplest form of data binding: `slider_1 = CTkSlider(app, command=progressbar_1.set)` — dragging the slider pushes its current value straight into `progressbar_1.set()` every tick so the two stay in sync.

  **Goal:** let the builder expose this pattern as a "Command Target" property on any command-capable widget, without dragging in the full Variables panel (which is a separate Phase 8 item above).

  **Schema side:**
  - Add a `Command Target` row to each command-capable descriptor.
  - New schema `type` `"widget_ref"` — renders as an enum dropdown whose options are populated from `project.iter_all_widgets()` at open time, filtered to widgets that expose a `.set(value)` method (CTkProgressBar, CTkSlider, CTkSwitch, CTkCheckBox, CTkRadioButton, CTkSegmentedButton, CTkComboBox, CTkOptionMenu). CTkLabel and CTkEntry need an adapter because they don't have a direct `.set(value)` (Label uses `configure(text=...)`, Entry uses `delete(0,"end") + insert(0, ...)`). First pass: only offer targets that have a native `.set`.
  - Store the target node id (UUID) in `node.properties["command_target"]`; editor shows the target's friendly name.
  - Cleared silently when the target is deleted or the target no longer has a `.set`.

  **Builder-side live preview:**
  - Workspace installs a bridge callback: on each `property_changed` for either side, or on widget creation, rebind `source_widget.configure(command=lambda v: target_widget.set(v))`.
  - Two widgets in the canvas then stay visually in sync — drag the slider, watch the progress bar fill.
  - Needs cleanup on widget destroy, parent reparent, and target clear.

  **Exporter side:**
  - Requires the exporter to know the target node's generated variable name when emitting the source widget. Today `_make_var_name` assigns names top-down in tree order so a sibling reference might not yet exist.
  - Fix: two-pass emit — pass 1 walks the tree and assigns `node_id → var_name`; pass 2 emits widgets using the full mapping.
  - Exporter then emits `source_var.configure(command=target_var.set)` as a line AFTER both widgets have been constructed (not in the constructor kwargs — that would require forward references).

  **New base class hook (probably):**
  - `export_post_lines(cls, var_name, properties, node_to_var: dict) -> list[str]` — like `export_state` but with access to the full id→var map so descriptors can emit cross-widget wiring.

  **Candidate source widgets that should expose `Command Target` first:** CTkSlider (highest ROI, pairs with ProgressBar), CTkSwitch, CTkSegmentedButton. The rest can follow.

  **Why deferred:** deferred from Phase 3 (CTkSlider session) because it needs the new `widget_ref` ptype + editor, the exporter two-pass refactor, and a per-widget `command=` wiring design that also has to cooperate nicely with the future Variables panel / Event Handlers items above — we don't want to paint ourselves into a corner.

---

## Notes / Ideas

> Free space — add anything that doesn't fit a phase yet.

- [x] სურათი ღილაკზე — already supported via Image + Text + Pos (compound)
- ჩარჩოს ფერი — `border_color` property for buttons/frames
- Configurable image size (currently hardcoded 20×20 in `transform_properties`)
- CTk corner_radius limitation note: CTk grows button to `text_w + 2*radius + padding`, so true small circles aren't possible with text — preview = reality, exported code matches
- **Semi-transparent images work out of the box** — PNG's alpha channel is preserved by PIL and respected by CTk's image rendering. Verified with `tools/test_transparent_png.py` using `Image.new("RGBA", ..., fill=(r, g, b, alpha))`. No workaround needed — the same PNG with 50% alpha blends correctly over any parent colour. Colour-level transparency (e.g. 50% red text) is **not** possible because Tk only accepts 6-char `#RRGGBB`; use image-based text if you truly need it.
- **`fg_color="transparent"` picker option** — for image-only buttons (no fill), the user has to type `"transparent"` into the colour field manually. Add a dedicated toggle / checkbox to the colour picker so the case is discoverable.
- **Drag PNG/JPG from Windows Explorer → workspace** — native Tk doesn't support OS file drag-drop. Adding it requires the `tkinterdnd2` PyPI package (lightweight, ~200 KB). Worth trying once the asset panel (Phase 7) lands so dropped files can auto-populate the project's `assets/` folder and auto-create a widget bound to the image.
- **Official CTk reference bundled** — `tools/fetch_ctk_reference.py` shallow-clones TomSchimansky/CustomTkinter and copies `examples/` + `test/manual_integration_tests/` into `reference/ctk_official/` (gitignored, ~9 MB). Used as visual + code reference when implementing new widget descriptors so our preview matches the official library's look. `reference/ctk_official/README.md` has the file map.
- **"Large Test Image" trick** — the official `image_example.py` "title-looking" gradient-with-text block is not a dynamic Label, it's a pre-rendered PNG (`test_images/large_test_image.png`) displayed via `CTkLabel(text="", image=CTkImage(...))`. If a user wants dynamic text on a gradient, the pattern is `CTkLabel(text="My text", image=<gradient-only PNG>, compound="center")` — same image trick, text overlay via `compound="center"`.
- **PyUIBuilder comparison** — PaulleDemon/PyUIBuilder is the closest competitor (2.3k stars, JavaScript/Electron, multi-framework: Tkinter + CustomTkinter + WIP Kivy/PySide). Ironically his **paid** ($29-49) premium features — save/load project files, dark theme, live preview, commercial use — are all **free** in this project. His advantages: multi-framework output, flex/grid layout managers, web-based distribution, ProductHunt + Discord ecosystem, requirements.txt generation, 3rd party plugin system. Our advantages: **preview = reality** (we ARE a CTk app, not a JavaScript approximation), native font scaling with zoom, real PNG alpha rendering, deep CTk integration via descriptor pattern (`transform_properties`, `derived_triggers`, `disabled_when`), Object Tree with multi-select + visibility/lock + drag-reparent, custom colour picker with tint strip + saved colours, Georgian UI + i18n readiness, no Electron overhead. Positioning: **"CustomTkinter's native Qt Designer — free, open source, always authentic preview"**.
