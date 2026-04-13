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

## Phase 3 — Remaining 14 Widget Descriptors

- [ ] CTkLabel
- [ ] CTkFrame
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
- [ ] Enable drag from the Widget Box **placeholder rows** as each descriptor ships (they already exist, just register in `app/widgets/registry.py`)
- [ ] Per-widget docs page under `docs/widgets/ctk_*.md` (help icon already wired to `{slug}.md`, just needs the file)
- [ ] **Perf check**: naive `disabled_when` re-evaluation in properties_panel `_on_property_changed` iterates all props on every change. For 15 widgets × ~5 disabled_when lambdas each, measure drag-time overhead. If noticeable, switch to dep-map approach (`TrackingDict` auto-detects which properties a lambda reads, builds `{trigger_prop: [dependent_props]}` map at rebuild time, so most changes hit O(1) dict lookup instead of O(N) re-evaluation).

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

## Phase 6 — Layout Managers

- [ ] Add `layout_type` field to each WidgetNode (pack / grid / place)
- [ ] "Layout" section in properties panel
- [ ] pack options (side, anchor, fill, expand, padx, pady)
- [ ] grid options (row, column, rowspan, columnspan, sticky)
- [ ] place options (relx, rely, x, y, anchor)
- [ ] Visual indicator on workspace (which manager is in use)
- [ ] Code exporter respects layout choices

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
