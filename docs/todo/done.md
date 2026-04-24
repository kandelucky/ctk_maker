# Done — შესრულებული ფაზები

> არქივი. თითოეული ფაზა ერთხაზიანი შემაჯამებელით. სრული დეტალები git history-ში.

---

## 2026-04 — Area QA passes + refactors

- **v0.0.20.1** (2026-04-24) — Indigo widget theme + README polish + competitor inspirations:
  - **Default widget colour** flipped from CTk's blue (`#1f6aa5` / `#144870`) to Tailwind Indigo 500 (`#6366f1` / Indigo 600 `#4f46e5` for hover) across every CTk descriptor that ships with `fg_color` / `hover_color` / `selected_color` / `progress_color` defaults — Button, CheckBox, RadioButton, Switch, Slider, SegmentedButton, Tabview, ProgressBar, OptionMenu. Builder UI chrome (toolbar, dialogs) still uses CTk's default blue — those render through CTk's own theme JSON, which would need a separate custom-theme pass.
  - **Builder-side accent colour** in `palette.py` (drag ghost), `dialogs.py` (RecentRow hover), `properties_panel_v2/panel_commit.py` (popup hover, color picker initial), `workspace/drag.py` (drop preview) flipped to the same Indigo so the design-time accents match the widgets being placed.
  - **Per-widget docs (`docs/widgets/ctk_*.md`)** updated to show the new default hex in their property tables.
  - **`tools/color_swatches.py`** — new throwaway script: a 10-button palette demo (Tailwind 500 picks: Indigo / Violet / Pink / Rose / Orange / Amber / Lime / Emerald / Teal / Cyan) that copies the picked hex to the clipboard. Used to settle on Indigo before the full sweep.
  - **README** — split the keyboard shortcuts table into a `Keyboard shortcuts` table and a new `Mouse actions` table (Middle-mouse drag pan, Ctrl+Wheel zoom, Click select, Ctrl+click toggle selection, Right-click context menu). Added F10 (Project window) to the keyboard table.
  - **`docs/todo/ideas.md`** — captured two CTkDesigner UX ideas worth borrowing later: a richer Export dialog (Default Mode / Theme / Scale / DPI Awareness / Default Page / OOP-code toggle) and JSON templates (Save / Insert reusable widget-tree blocks).

- **v0.0.20** (2026-04-24) — Asset tokens + project-scoped Image picker (Phase B-2):
  - **`app/core/assets.py`** — `asset:images/<name>` token utilities: `is_asset_token`, `parse_asset_token`, `make_asset_token`, `resolve_asset_token` (token → abs path against a project file), `absolute_to_token` (in-assets abs path → token, else None), `copy_to_assets` (file picker / drop target → SHA-deduped copy with collision-safe filename).
  - **Project save/load round-trip** — `project_saver._tokenize_image_paths` walks the serialized doc tree and rewrites any in-assets absolute `image` property to the portable token form; `project_loader._resolve_image_tokens` does the reverse on read so descriptors keep seeing plain absolute paths in memory.
  - **`Project.path` attribute** — mirrors MainWindow's `_current_path` so the assets layer can answer "which project am I in?" without having to thread MainWindow through every call site.
  - **`app/ui/image_picker_dialog.py`** — new project-scoped Image picker (replaces the bare `filedialog.askopenfilename` in `_pick_image`). Lists every image already in `<project>/assets/images/` with thumbnails; the "+ Import image..." button copies a file from anywhere on disk into the project (deduped). The OS file picker is no longer accessible directly — every Image reference now lives inside the project, which keeps `.ctkproj` portable.
  - **Help icon + tooltip** in the picker header explains the project-only model and the difference between Import and Pick.
  - **Exporter — relative asset paths + side-car copy.** `_path_for_export` rewrites any in-assets absolute path emitted via `Image.open(...)` / `_tint_image(...)` to a `assets/<rel>` relative path; `export_project` then `shutil.copytree`s the project's `assets/` folder next to the exported `.py` so the relative paths resolve when the user runs it.

- **v0.0.19.1** (2026-04-24) — Project window (Phase B-1) + untitled removal:
  - **New `app/ui/project_window.py`** — `ProjectPanel` (embeddable) + `ProjectWindow` (floating, F10 / View → Project) showing the current project's name, folder path, and a tree view of `assets/{images,fonts,sounds}/`. Header has a "Reveal in Explorer" button (uses `os.startfile` on Windows, `open`/`xdg-open` elsewhere); footer has "+ Add Image..." (file picker → `assets/images/`, dedupe by SHA256 so re-adding the same file doesn't write a second copy, filename collision resolves with `_2`, `_3` suffixes).
  - **Untitled-project state removed.** `New Untitled` menu entry, the `on_new_untitled` toolbar callback, and the corresponding `_on_new_untitled` MainWindow handler are all gone — every project must come from the New Project dialog (with folder structure) or be opened from disk. The startup dialog drops its `Cancel` button; closing it via X / Escape now triggers a "Quit CTkMaker?" confirmation that destroys the main window when confirmed.
  - **Bug — Name entry growing on every typed char:** the live preview label below the Save to row was un-bounded, so each char typed extended the label width which dragged the dialog (and the Name entry's `fill="x"`) wider. Pinned the label to a fixed 58-char visual width and added a `len > 56 → mid-front truncation` rule on the preview text.
  - **Bug — Screen Size dropdown out of sync with W / H defaults:** the form hardcoded the dropdown label to `Medium (1024×768)` regardless of the caller-supplied default_w / default_h. New `_label_for_size()` helper now finds the matching device + preset for a given W×H pair (falls back to `Custom`).
  - **Bug — Open / Recover dialogs still labeled `CTk Builder project`** — flipped to `CTkMaker` in `main_window.PROJECT_FILE_TYPES` and `startup_dialog._on_browse`.

- **v0.0.19** (2026-04-24) — Project folder structure (Phase A — assets foundation):
  - **New `app/core/paths.py`** with `get_default_projects_dir()` (returns `~/Documents/CTkMaker/`, auto-created), `project_folder()`, `project_file_in_folder()`, `assets_dir()`, and `ensure_project_folder()` (creates the folder + `assets/{images,fonts,sounds}/` skeleton).
  - **New Project dialog** now defaults `Save to` to `~/Documents/CTkMaker/` instead of Desktop, and renders a live preview line right under the Save to row showing the resolved `<save_dir>/<name>/<name>.ctkproj` target so the user sees exactly where the project will land.
  - **Form validation** now refuses to overwrite an existing folder (warning dialog instead of silent overwrite) and pre-creates the project folder + `assets/` skeleton before the first save lands.
  - **`save_project` defensive `parent.mkdir(parents=True, exist_ok=True)`** so Save As to an arbitrary location doesn't fail on a missing parent.
  - Legacy single-file projects keep loading unchanged — they just don't get the folder skeleton until the user moves them by hand.
  - **Phase B (asset tokens, image copy on pick, exporter relative paths)** and **Phase C (Project panel UI — file tree, drag-to-canvas, sidebar dock)** scoped for upcoming iterations.

- **v0.0.18.3** (2026-04-24) — Rename: CTk Visual Builder → CTkMaker:
  - **Display name** flipped across every user-facing surface — main window title, AboutDialog, StartupDialog, project_loader error messages, exported-code header comment, README, all `docs/*.md` pages, `run.bat` console title, `tools/text_editor_dialog.py` docstring.
  - **GitHub URLs** updated from `kandelucky/ctk_visual_builder` to `kandelucky/ctkmaker` (main_window's docs URL + Properties panel's wiki link). Repo rename to `ctkmaker` happens on github.com; the auto-redirect handles legacy links during transition.
  - **Per-user config dir** (`~/.ctk_visual_builder/settings.json` / `recent.json`) intentionally kept as-is to avoid orphaning existing user data on first launch. Migration to `~/.ctkmaker/` scheduled in roadmap alongside the untitled-autosave spool dir (single touch of the root folder for both).
  - Reference: Akascape's `CTkDesigner` ([ctkdesigner.akascape.com](https://ctkdesigner.akascape.com/)) is a direct competitor — same author as CTkScrollableDropdown — and is why the user's first preferred name was unavailable.

- **v0.0.18.2** (2026-04-24) — Autosave + Recover from Backup menu:
  - **`AutosaveController`** in `app/core/autosave.py` — every 5 minutes (configurable via `autosave_interval_minutes` in settings) while the project is dirty AND has a saved path, writes the current state to `<path>.autosave` via atomic `.tmp` + `os.replace`. Skipped for untitled projects (no path = no autosave); Phase 2 will spool them to a per-user dir.
  - **No-op tick skip** — controller snapshots the history's top marker after every successful write and compares it on the next tick; if the user hasn't edited (or has undone back to the last-autosaved state), the tick is a no-op so a long idle period doesn't rewrite the same `.autosave` content every minute. The marker is reset whenever `dirty_changed -> False` fires (explicit save or undo back to the saved marker) so the next dirty cycle starts fresh.
  - **Cleared on explicit save** (`_on_save`, `_on_save_as`, `_on_new`) and on the user's "Discard" answer to the unsaved-changes prompt — so a deliberate throw-away doesn't reappear as a "restore from autosave?" prompt next launch.
  - **`_open_path` recovery** — if a sibling `.autosave` exists AND its mtime is newer than the saved file, the loader prompts the user with the autosave timestamp; restoring loads the autosave content, marks the project dirty, and clears the autosave file so the next explicit save writes the recovered content back into the real `.ctkproj`.
  - **File → Recover from Backup...** menu entry between Open and Recent Forms; opens a `.ctkproj.bak` directly via the standard load path, then forces an untitled state so a reflexive Ctrl+S can't blindly overwrite the (likely damaged) original sitting next to the backup. Info dialog explains the Save As requirement.

- **v0.0.18.1** (2026-04-24) — `.bak` on save (minimal viable backup):
  - **`save_project` rotates the previous file** via `os.replace(path, path.bak)` before writing the new JSON. Atomic on Windows + POSIX, overwrites any prior `.bak` so one generation is kept. If the new write fails (disk full, permission flip), the `.bak` still holds the last good copy.
  - **Damaged-project dialog** now checks for the `.bak` sibling and tells the user where to recover from — replaces the previous "if you have a backup" hand-wave that was a polite fiction.
  - **New helper `backup_path_for(path)`** in `project_saver` so callers (loader recovery message today, future Restore-from-Backup menu entry tomorrow) share one source of truth for the convention.

- **v0.0.18** (2026-04-24) — ScrollableDropdown helper for ComboBox + OptionMenu:
  - **New `app/widgets/scrollable_dropdown.py`** — Toplevel-based popup that replaces CTk's character-width-based `DropdownMenu`. Width matches `attach.winfo_width()`, scrollbar appears past `max_visible`, popup frame is a full CTkFrame with configurable border / radius / fg.
  - **CTkOptionMenu two-click selection** — first click selects, follow-up click within 500 ms opens; afterwards plain clicks just keep the selection (no surprise popups). Wired in `_bind_widget_events` via a wrapped `_open_dropdown_menu`.
  - **New "Dropdown Layout" property group** for both widgets: `dropdown_offset`, `dropdown_button_align` (left / center / right), `dropdown_max_visible`, `dropdown_corner_radius`, `dropdown_border_enabled` + `dropdown_border_width` + `dropdown_border_color`.
  - **Outside-click-to-close** — `<FocusOut>` on overrideredirect Toplevels was unreliable on Windows (popup vanished on first frame); replaced with `<Button-1>` on the parent toplevel that hides only when the click lands outside both the popup and the attach widget. Toggle behaviour: clicking the attach while the popup is open closes it.
  - **Toplevel bg sync** — `tk.Toplevel` background now matches popup `fg_color` so the rounded `CTkFrame` corners don't reveal the system gray underneath as a "ghost popup".
  - **Deferred rebuild** — building children inside a withdrawn Toplevel left CTkScrollableFrame in a bad layout state (text invisible after a `max_visible` change). `configure_style` now flags `_buttons_dirty` when withdrawn and rebuilds inside `show()` after `deiconify`.
  - **Edit Values vs Edit Segments vs Edit Tabs** — segment_values editor button label and dialog title now branch on `widget_type`: `tab_names` → "Edit Tabs", `CTkSegmentedButton` → "Edit Segments", everything else → "Edit Values".
  - **Exporter integration** — `_emit_widget` emits `widget._scrollable_dropdown = ScrollableDropdown(widget, ...)` for every CTkComboBox / CTkOptionMenu, `generate_code` adds the import, `export_project` side-cars `scrollable_dropdown.py` next to the export so Preview and exported apps both render the new popup.
  - **widgets.md** — CTkScrollableFrame, CTkTabview, CTkComboBox, CTkOptionMenu sections all green; `[!]` deferred entries removed; Findings updated with the v0.0.17 SF/Tabview resolutions and the v0.0.18 dropdown work.
  - **ideas.md** — Phase 2 dropdown polish (per-item font, button height, unified arrow icon, ComboBox text-input tooltip) carried over.

- **v0.0.15.24** (2026-04-22) — Image QA + color editor polish:
  - **Image widget** — Area 7 QA passed. All 7 checks: palette drop, image picker + clear, preserve_aspect, tint, fg_color transparent, missing path placeholder, export as CTkLabel.
  - **Tint Color / image_color clear UX**: `clear_value` changed `None` → `"transparent"` (same as `fg_color`) so the ✕ button dims and shows "none" when no tint is set. Same fix applied to CTkButton's `image_color` / `image_color_disabled`.
  - **`_is_cleared` fix**: `None` and `"transparent"` are now treated as equivalent cleared sentinels so `_is_cleared(None, "transparent")` returns `True`. ✕ cursor changes `"hand2"` ↔ `"arrow"` based on cleared state; click is a no-op when already cleared.
  - **`format_value` for color**: `None` now surfaces as `"              none"` matching `"transparent"`. Empty string still returns `""`.
  - **Exported clipboard helper docstring** simplified.
  - **ComboBox `dropdown_width` cleanup**: added to `_NODE_ONLY_KEYS` so old project files that accidentally stored it don't crash on open.

- **v0.0.15.23** (2026-04-22) — Area 7 batch 2: SegmentedButton / Tabview / ComboBox / OptionMenu / ScrollableFrame + small fixes across widgets:
  - **CTkSegmentedButton / CTkTabview / CTkComboBox / CTkOptionMenu** — `values` / `tab_names` fields switched from multiline text editor to new `segment_values` ptype (single "Edit..." button opens a scrollable +/- table dialog via `SegmentValuesDialog`). `initial_value` / `initial_tab` fields switched to `segment_initial` ptype (dynamic dropdown reading sibling values prop at popup time).
  - **CTkSegmentedButton** post-edit selection fix — `_bind_widget_events` is now idempotent (`_ws_bound_nid` flag); workspace re-walks children after every `configure()` so CTk's internally-rebuilt segment buttons regain event handlers.
  - **CTkSegmentedButton** icon → `panel-left-right-dashed`.
  - **CTkTabview** — `initial_tab` applied via `widget.set()` in `apply_state` + emitted in `export_state`. Tab names guard (last tab undeletable in dialog).
  - **CTkSlider** — disabled visual (grey color override for track/progress/button in `transform_properties` + `export_kwarg_overrides`). corner_radius / button_length / button_corner_radius min → 1. button_length default → 1.
  - **CTkProgressBar** — corner_radius min → 1.
  - **CTkEntry** — disabled visual (dim fg/text/border). Focus-lost bug in preview/export fixed: `_setup_text_clipboard` now also binds `<Button-1>` globally to defer `root.focus_set()` on non-text clicks, triggering CTk's `_entry_focus_out` → placeholder restore.
  - **CTkFrame / layouts** — `layout_spacing` hidden (not just dimmed) for `place` layout. CTkScrollableFrame: Layout group removed; scrollbar track color clearable.
  - **New files**: `tools/segment_values_dialog.py`, `app/ui/properties_panel_v2/editors/segment_values.py`, `panel-left-right-dashed.png`.
  - **Inspector right-click context menu** extended to `segment_values` editor + `segment_initial_options` reads both `values` and `tab_names` for dynamic dropdown.

- **v0.0.15.22** (2026-04-22) — CheckBox / RadioButton / Switch text alignment + radio group export + small fixes:
  - **4-way text position + spacing** for CheckBox / RadioButton / Switch (Inspector → Text → Text Position dropdown left/right/top/bottom + Text Spacing 0–100). Re-grids CTk's internal `_canvas` / `_text_label` / `_bg_canvas` (private reach — same trade-off as the Button text-hover work). bg always covers the full widget area via `rowspan=3, columnspan=3` so top/bottom layouts don't leave a misaligned background. Cursor preserved (snapshot outer cursor before re-grid, propagate to children after). Re-grid is gated on actual position/spacing change so unrelated property edits don't disturb cursor state.
  - **Exporter helper** `_align_text_label(widget, position, spacing)` emitted once per project that uses the feature; covers all three widget types via a shared internal layout. New `text_position` ptype + `TEXT_POSITION_OPTIONS` constant + format_utils + editors registry.
  - **CTkRadioButton group → real shared `tk.StringVar` in exports**: previously each radio was emitted standalone, so groups didn't actually deselect each other in the runtime app. Now the exporter pre-scans every radio per document, builds a `radio_var_map`, declares `self._rg_<group> = tk.StringVar(value="")` once at the top of `_build_ui`, and threads `variable=...` + `value="r1"/"r2"/...` through each radio's constructor. Initially-checked group radios prime the var via `.set("rN")` instead of the standalone `.select()`. Standalone radios (no group) keep the old path.
  - **CTkRadioButton schema cleanup**: removed `border_color` and the dead Border subgroup (the subgroup preview displayed "not active" because radios don't have a `border_enabled` toggle; the colour change wasn't visible enough to be worth the noise). `border_width_unchecked` / `border_width_checked` now sit directly in Rectangle.
  - **CTkSwitch corner_radius default 1000 → 9** (= half of default switch_height for the same fully-rounded pill look without an absurd Inspector value).
  - **CheckBox / Radio / Switch default geometry 100×24 → 20×10**: the widget auto-grows around its content so the bg matches the actual checkbox + label region, not the configured rectangle. Stops the bg looking misaligned when `text_position` moves the label off-axis.
  - **ideas.md** — RadioButton "alternate selection visuals" (icon mode + true filled center) added under Smaller ideas; Preview lockout + topmost deferred to "Smaller ideas".

- **v0.0.15.21** (2026-04-22) — Cross-cutting Area 7 polish + Button text-hover:
  - **Property panel — right-click context menu on inline editors**: every double-click overlay (`tk.Entry` for both string and number rows) gets Cut / Copy / Paste / Select All. Number rows additionally get **Min: \<value>** / **Max: \<value>** quick-fill rows that resolve schema lambdas against the current widget's properties (so context-sensitive bounds like `corner_radius ≤ min(width, height)/2` show the right cap).
  - **Exported app — text clipboard helper**: when a project includes any CTkEntry / CTkTextbox / CTkComboBox, the generator emits a `_setup_text_clipboard(root)` helper once at the top and calls it after `app = MainWindow()`. The helper binds `<Button-3>` (right-click → Cut/Copy/Paste/Select All menu) and a keycode-based `<Control-KeyPress>` router on every `tk.Entry` and `tk.Text` widget. Copy/cut detection handles both `selection_present()` (Entry) and `tag_ranges("sel")` (Text). Works on Latin AND non-Latin layouts (Georgian, Russian, …) because the router falls back to hardware keycodes (Windows VK 67/86/88/65) when the keysym isn't a Latin letter. Same code runs in `Ctrl+R` preview and File → Export.
  - **CTkButton Text → Hover Color Effect**: new `text_hover` boolean + `text_hover_color` colour row in the Text group. Hover swap reaches into `_text_label` directly (NOT `widget.configure(text_color=...)`, which would route through CTk's `_draw()` and reset the hover background mid-hover). Bind-once-per-widget + read live `_auto_hover_*` attrs at handler time sidesteps tkinter's buggy `unbind(seq, funcid)`. Force-restore to normal colour when the toggle flips off mid-hover. Exporter emits matching `_auto_hover_text(button, normal, hover)` helper + per-button call when `text_hover=True`.
  - **CTkButton schema reshuffle**: Hover Effect boolean moved from Main Colors → Button Interaction (next to Interactable). Image & Alignment group renamed → "Icon".
  - **Inspect CTk Widget — fixed app-wide ttk theme leak**: removed the rogue `style.theme_use("clam")` call that wiped Object Tree + Properties panel styling whenever the inspector window opened. ttk.Style is a global singleton; named-style configure on top of the active theme is enough.
  - **Inspect CTk Widget — palette CATALOG as source**: dropdown now lists every palette entry (Vertical / Horizontal / Grid Layout show separately even though they share `CTkFrameDescriptor`), with `preset_overrides` applied to the Builder column. Schema `hidden_when` is honoured so vbox/hbox presets don't surface irrelevant `grid_rows` / `grid_cols` rows.
  - **CTk warning silenced**: `_show_empty` was passing `image=""` to a CTkLabel — flipped to `image=None`.

- **v0.0.15.20** (2026-04-22) — Tools panel + grid shrink guard:
  - **Tools → Inspect CTk Widget...** — new menubar entry opens a Toplevel comparing every palette widget against the actual CTk constructor signature (read at runtime via `inspect.signature`). Three-status table per row: ✓ exposed by builder, ⚠ CTk-only (typically runtime kwargs like `command` / `textvariable`), ★ builder helper (x/y, font_*, border_enabled toggle, etc.). Honours per-row `hidden_when` lambdas so vbox/hbox presets hide irrelevant grid_rows/grid_cols. Window stays on top of the builder (`transient` + post-render `lift`), reuses a single instance instead of stacking.
  - **`tools/inspect_ctk_widget.py`** — standalone CLI helper that prints any CTk widget's `__init__` signature in coloured ANSI. Forces UTF-8 stdout so cp1252 consoles don't crash. Source of truth note: the official customtkinter doc site is incomplete — checkmark_color, bg_color etc. only show up via the actual signature.
  - **Grid shrink guard** (panel_commit.py): when committing a smaller `grid_rows` / `grid_cols`, scan children for the max occupied row/column and reject the change with a dialog if any child would be orphaned. Spinner snaps back to the stored value via `_refresh_cell`.

- **v0.0.15.19** (2026-04-22) — Area 7 (Widgets) — CTkButton + CTkLabel + CTkEntry + CTkTextbox pass + multiple feature additions:
  - **Disabled icon tint export**: when a button has both `image` and `image_color_disabled`, the exporter emits TWO tinted CTkImages (`self.{var}_icon_on` / `self.{var}_icon_off`) plus an `_apply_icon_state(button, on, off, state)` helper. Comment above each affected button shows the call signature. Builder pops a one-shot advisory when the user picks `image_color_disabled` (dismissable via "Don't show again" → settings).
  - **Settings → Reset Dismissed Warnings**: clears every `advisory_*` flag so dismissed dialogs surface again on their next trigger.
  - **CTkLabel cleanup**: `text_color_disabled` removed (Label has no state, the field was meaningless); `fg_color` (Background) added with clearable ✕ → "transparent". Outer `bg_color` deliberately not exposed — too rarely useful, only matters with rounded corners on a Label.
  - **CTkButton additions**: `border_spacing` (Inner Padding) row + `hover` boolean toggle (with `disabled_when` dimming `hover_color` when off). Button palette icon refreshed `square` → `square-dot` (paired with the deferred FX Button experiment on its branch).
  - **CTkEntry overhaul**: placeholder bug fix (apply_state was wiping CTk's placeholder text on every property change; now respects `_placeholder_text_active` flag and skips no-op refreshes), `password` boolean → `show="•"` export, `readonly` boolean (independent of Interactable, three-way state normal/disabled/readonly), `justify` enum (Left/Center/Right). Export `export_state` flips state to "normal" before insert when target is disabled/readonly so initial text actually lands.
  - **CTkTextbox addition**: `wrap` enum (none/char/word) Content row. Wired through new shared `WRAP_OPTIONS` + `wrap` ptype in the Inspector enum infrastructure.
  - **Run Python Script** action: pick any local `.py` and launch it as a subprocess. Wired into the toolbar (`tv-minimal-play` icon between Export and Undo) and File menu (Run Python Script…). Extension validation rejects non-`.py`/`.pyw` upfront with a clear dialog. Last-used directory remembered in settings.
  - **Palette ghost colour**: drag preview now pulls `fg_color` from the dragged descriptor's defaults (so each widget's ghost matches its drop result) instead of the hardcoded CTk blue.
- **v0.0.15.18** (2026-04-21) — Area 6 (Multi-document) QA pass complete: 54/54. Send-to-back now works on active Main Window even at docs index 0 (deactivates, promotes next topmost). AddDialogSizeDialog clamps to 100–4000 with warning dialog. Single-document export: `generate_code(single_document_id=...)` emits one doc as a standalone `ctk.CTk` subclass; wired into File → Export Active Document... and a new per-dialog Export icon in the chrome.
- **v0.0.15.17** (2026-04-21) — Area 5 QA completion + main_window.py refactor. Final batch of project-lifecycle fixes (per-document widget name counters, clearer error dialogs for corrupt / missing / wrong-version files, default window name tracks project name). Image tint path normalisation on export. Dialog ▶ preview button. main_window.py split via mixins: `main_menu.py` (376 lines, MenuMixin — menubar + Edit-menu dispatchers + Recent Forms submenu) and `main_shortcuts.py` (212 lines, ShortcutsMixin — keyboard bindings, non-Latin keycode router, Ctrl+Z/Y auto-repeat guards). 1234 → 753 lines on the core class.
- **v0.0.15.16** (2026-04-21) — Area 5 (Project lifecycle) pass + multiple fixes. `load_project` clears history (no ghost undo from closed project). Recent Projects: startup dialog dims missing rows, File menu hides them. HBox/VBox `grow` equal-split resizes every sibling, not just the one being re-applied. Click logic revised — drill only on a fast (< 800 ms) second click on the same leaf; child-depth sticks within a branch so dragging the parent isn't kidnapped into children. Image tint exports via PIL `_tint_image` helper — one PNG, unlimited runtime colour variants. Dirty flag rerouted through a history-top marker — Ctrl+Z back to saved state auto-clears the `•`. Project file error dialogs rewritten in plain language (damaged / missing / wrong-version). Default window name now tracks project name (`Untitled` until New dialog sets it). Dialog chrome gained a ▶ preview button (hidden-root host, one preview window per dialog at a time). Main preview (Ctrl+R) + per-dialog preview both dedup — extra clicks are no-ops until the existing window closes. Add Dialog scrolls the canvas onto the new form.
- **v0.0.15.15** (2026-04-21) — Area 4 (Commands) QA pass complete: 42/43 tests. Fixed Ctrl+Z / Ctrl+Y key-auto-repeat spam — one press = one undo.
- **v0.0.15.14** (2026-04-21) — CTkSlider orientation flip now works (added `init_only_keys` + `recreate_triggers` + `on_prop_recreate` width/height swap matching CTkProgressBar); `button_corner_radius` min raised 0→1 to avoid CTk internal visual split bug.
- **v0.0.15.13** (2026-04-21) — Grid / managed-layout child jump fix: non-geometry prop change (corner_radius / text / image) on a grid/vbox/hbox child no longer pulls it to parent's (0, 0).
- **v0.0.15.12** (2026-04-21) — panel.py refactor: SchemaMixin + CommitMixin split. 1378 → 682 ხაზი.
- **v0.0.15.11** (2026-04-21) — Area 3 (Properties panel) QA pass complete: 38/42 tests + 6 bug fixes.
- **v0.0.15.10** (2026-04-20) — DPI canvas fix (canvas_scale = zoom × DPI) + Inspector geometry bounds clamp.
- **v0.0.15.9** (2026-04-20) — Inspector UX polish: clearable ✕ color button, drag-scrub cursor fix, Object Tree menu fix.
- **v0.0.15.8** (2026-04-19) — Layout module refactor + dead-code sweep.
- **v0.0.15.7** (2026-04-19) — Area 2 (Layout managers) QA pass complete: 44/44 tests + 7 bug fixes, numeric spinner.
- **v0.0.15.2–15.6** — Area 1 (Workspace core) QA + refactor rounds.
- **v0.0.15** (2026-04-18) — Area 1 QA pass complete: 38/38 tests + 10 bug fixes.

## Phase 2.x — Properties panel, UI polish, refactors

- **Phase 2.14** (2026-04-16) — Panel visual unification: all scrollbars transparent trough, unified headers.
- **Phase 2.13** (2026-04-15) — Object Tree dock (Panel split from Toplevel) + Image widget descriptor.
- **Phase 2.12** (2026-04-14) — Properties panel UX polish + docs (DragScrub extract, Corner Radius flatten, CTkLabel docs).
- **Phase 2.11** (2026-04-14) — Refactor round 2: ZoomController extract, v2 panel package split, architecture dashboard.
- **Phase 2.10** (2026-04-14) — Refactor + icon system: NewProjectForm + RecentList extract, icon tinting, fresh Lucide set.
- **Phase 2.9** — Dirty tracking + QoL: title bullet, confirm-discard, Georgian font + non-Latin shortcut fallback.
- **Phase 2.8** — Startup dialog + File → New rewrite (recent list, device presets, validation).
- **Phase 2.7** — Workspace canvas + editor UX: document rect, scrollbars, dot grid, zoom, Hand tool, status bar.
- **Phase 2.5** — Palette / Widget Box polish: Qt Designer-style Widget Box, filter entry, collapsible groups.
- **Phase 2** — Toolbar + Persistence + Menubar: save/load (.ctkproj v1), export, preview, theme, shortcuts.

## Phase 6.x — Layout managers

- **Phase 6.6** (2026-04-17) — Grid place-based centring + workspace refactor (widget_lifecycle extract).
- **Phase 6.5** (2026-04-17) — Grid WYSIWYG + drag-to-cell + runtime parity.
- **Phase 6.4** (2026-04-17) — Stage 3 real pack() for vbox/hbox + Layout presets + workspace package split.
- **Phase 6.3** (2026-04-16) — Layout managers split (pack → vbox + hbox) + icons (rows-3 / columns-3 / grid-3x3).
- **Phase 6** stage 1+2 (2026-04-16) — Layout managers data model + export + visual feedback (badges, chrome suffix).
- **Phase 6.1** — WidgetNode parent/children tree data model.
- **Phase 6.2** — Hierarchical rendering: nested widgets via `widget.place()`, delta-based drag math.
- **Phase 6.3 drop-to-reparent** — `_find_container_at`, palette drop into container, drag-to-reparent.
- **Phase 6.4 sibling reorder** — Object Tree drag with 3 drop zones + insertion line.
- **Phase 6.5 nested code export** — depth-first exporter walks tree, emits parent-before-children.
- **Phase 6.6 Object Tree polish** — type filter dropdown, name search, visibility + lock toggles, multi-select.

## Phase 5.x — Window Settings + Multi-document

- **Phase 5.5** — Multi-document canvas: Main Window + N Dialogs per project, chrome drag, cross-doc widget drag.
- **Phase 5** (partial — v0.0.8) — Window Settings: virtual WINDOW_ID node, chrome title-bar, dirty indicator.

## Phase 7 — Select / Edit tool separation

- **Partial** — Select + Edit tools, Ctrl+click multi-select, group drag, cross-document group drag, layout-child safety, locked widget pass-through, Edit button in Select-mode panel header.
- Remaining items moved to [roadmap.md](roadmap.md).

## Phase 3 — Widget Descriptors (13 / 15 full + 2 partial)

- CTkButton, CTkLabel, CTkFrame, CTkCheckBox, CTkComboBox, CTkEntry, CTkOptionMenu, CTkProgressBar, CTkRadioButton, CTkSegmentedButton, CTkSlider, CTkSwitch, CTkTextbox + Image descriptor.
- Partial: CTkScrollableFrame, CTkTabview (nesting children deferred → roadmap).
- Shared infrastructure: `init_only_keys`, `recreate_triggers`, `apply_state`, `export_state`, `canvas_anchor`, `_safe_bind`.

## Phase 1 — Core Interactions

- Drag-to-move, x/y live sync, 8 resize handles, per-handle cursors, Delete key, context menu, Esc deselect, palette drag-drop, arrow nudge (Shift=10px), Bring to Front / Send to Back, drag perf.

## Phase 0.5 — Property Editor Enhancements (partial)

- Drag-to-scrub, Alt fine mode, min/max clamp, dynamic max lambda, anchor / compound / image editors, property groups, subgroups, paired layout, color picker (HSV/HSL, tint strip, saved colors), eyedropper (external library), auto-fit text.
- Remaining: Reset-to-default, Tooltip, collapsible groups, Arrow-key ±1 → [roadmap.md](roadmap.md).

## Phase 0 — MVP

- Three-panel layout, event bus, Project model, WidgetNode, descriptor pattern, CTkButton, click-to-add, selection, live property editing.

---

- 2026-04-23 v0.0.15.25 — Area 8 start: Object Tree UX — inline rename (double-click), type initials + layout-aware Frame variants, Order column, larger arrows, filter active-doc-only + blue tint indicator, Name field disabledbackground fix, CTkLabel icon clear fix, right-click menu disabled items foreground fix, Enter defocuses Name field, right-click on Name field
- 2026-04-23 v0.0.15.26 — History panel docked in sidebar (Tree/History toggle buttons), click-to-jump in history, accent borders removed from Object Tree + History + Properties, Properties title label removed, Properties tab header added, HistoryPanel extracted as reusable CTkFrame
- 2026-04-23 v0.0.15.27 — File menu: New Untitled (file-plus-corner icon, no save dialog), Save As icon→save-all, Close removed; toolbar: on_new_untitled wired
- 2026-04-23 v0.0.15.28 — Widget menu (cascades per group), palette regrouped: Layouts/Containers/Buttons/Display/Selection/Input
- 2026-04-23 v0.0.15.29 — Form menu redesign: Preview Active, Remove/Move Up/Down with dim state, Rename, Form Settings, All Forms submenu (dynamic doc list + center on click); screenshot idea saved to ideas.md
- 2026-04-23 v0.0.15.30 — About dialog (custom tk.Toplevel, clickable library links), Settings menu disabled
- 2026-04-23 v0.0.15.31 — Workspace bar: Preview/Preview Active (square-play/play icons, dim state), All Forms dropdown, Containers moved to bottom; toolbar: save icon, preview removed, tooltip above cursor, single separator; palette/menu regrouped
- 2026-04-23 v0.0.15.32 — Shortcuts: Ctrl+D/X/I/P/M/A/Shift+I added, Georgian fallback; Edit menu: Cut+Duplicate+Rename; Form menu accelerators; Help: Documentation+Ctrl+Shift+I; README shortcuts table
- 2026-04-23 v0.0.16 — Area 8 complete: 100/103 tests passed; testing docs updated; theme toggle deferred to bugs.md
- 2026-04-24 v0.0.17 — Containers: CTkTabview + CTkScrollableFrame now real drop targets. Tabview — `parent_slot` on WidgetNode (tab name, save/load round-trip), palette drop + reparent-drag into active tab, tab-switch hook redraws selection chrome, single-tab rename auto-migrates children (multi-change shows Continue/Back confirm via new ConfirmDialog), Tab Bar Position (top/bottom) + Align (left/center/right/stretch) via CTk anchor + manual `_set_grid_canvas`/`_set_grid_current_tab` on live change, Initial Tab default "Tab 1", "Edit Segments" → "Edit Tabs" label. ScrollableFrame — vbox/hbox pack model driven by orientation (children auto-stack, scrollbar engages when content overflows), outer `_parent_frame` pinned in export to match builder. ReparentCommand captures old/new `parent_slot`. Nested-widget DPI drag bug fixed: CTk overrides `.place` with DPI scaling but NOT `.place_configure` — unified all nested placement through `.place(...)`. Selection chrome hides via `winfo_ismapped` for widgets in non-active tabs. Composite canvas-item sizing uses `canvas_scale` (was `zoom.value`) so SF outer matches plain Frame at 150% DPI. `_disable_container_propagate` leaves inner frame propagating so SF grows with packed children.
