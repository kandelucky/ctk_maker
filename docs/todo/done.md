# Done — შესრულებული ფაზები

> არქივი. თითოეული ფაზა ერთხაზიანი შემაჯამებელით. სრული დეტალები git history-ში.

---

## 2026-04 — Area QA passes + refactors

- **v0.0.28** (2026-04-26) — Preferences + Export dialogs:
  - **`SettingsDialog`** (`app/ui/settings_dialog.py`) — tabbed Preferences window opened via `Settings → Preferences...` or `Ctrl+,`. Five tabs (in order): Defaults / Workspace / Autosave / Notifications / Appearance. Defaults tab covers New-Project save location + width × height, Workspace tab covers builder grid (style / hex color with picker swatch / spacing px), Autosave tab covers the interval (already wired in `autosave.py`, just exposed in the UI), Notifications tab is a "Reset dismissed warnings on OK" checkbox + explainer, Appearance tab is the theme dropdown (parked disabled with a "coming soon" hint until the Light theme polish lands). 600×500, dark dropdown palette so option menus blend with the surrounding panels.
  - **`get_default_projects_dir()` reads settings first** — the helper consulted only `~/Documents/CTkMaker/` before; now it tries `default_projects_dir` from settings.json, falls back to Documents, then to `~/CTkMaker/` if even Documents is read-only. `StartupDialog` reads `default_project_width` / `default_project_height` via the new `get_default_project_size()` helper so the welcome screen pre-fills the user's picked sizing.
  - **Global builder grid override** — `_draw_grid_for_doc` now reads `grid_style` / `grid_color` / `grid_spacing` from settings.json first, falling back to the document's own `window_properties` only when a key is missing. Set the grid once in Preferences and every document in every project picks it up; per-document Window Settings stays loadable for projects authored before the global override existed. The Preferences dialog's `on_workspace_changed` callback triggers `renderer.redraw()` so the change lands without a relaunch.
  - **Settings menu cleanup** — the duplicated `Appearance Mode` cascade and `Reset Dismissed Warnings` entry both moved into the Preferences dialog; the Settings menu now holds only the `Preferences...` entry. `Ctrl+,` accelerator wired through `main_shortcuts._bind_shortcuts`.
  - **`ExportDialog`** (`app/ui/export_dialog.py`) — replaces the bare `asksaveasfilename` step for File → Export and the per-document chrome Export icon. Mirrors the New Project dialog visually — rounded `CTkFrame` panel, "Export Project" subtitle, label-aligned rows, italic preview line under Save to, footer with primary `Export` button.
    - Split path entry: separate `Name` (filename stem; auto-named after the chosen scope) + `Save to` (folder; sticky once the user changes it). Defaults land at `<project>/exports/<scope>.py` and the folder is auto-created on Export.
    - Folder icon button next to Save to opens `askdirectory` for a folder-only browse.
    - Scope dropdown (220 px wide) lists `All forms (Main + N Dialogs)` plus each document by name; an italic `"N forms in project"` info label sits next to it.
    - `After:` row carries two independent checkboxes — `Open in editor` (uses the OS edit verb so .py opens in IDLE / VSCode / Notepad++ instead of running) and `Run preview` (spawns the exported file with the running Python interpreter, matching `Preview ▶`). A sub-hint below the row spells out what each does.
  - **`RELEASE_CHECKLIST.md`** + **`LICENSE`** (MIT) committed alongside so the repo's release-prep state is captured.

- **v0.0.27** (2026-04-26) — Test consolidation + bug sweep:
  - **Lucide picker default category** changed from `"All"` (~400 cells rendered up front) to the first sorted category (`Accessibility`, ~30 icons). The "All" entry stays in the sidebar — opening the picker is now near-instant instead of laggy.
  - **Lucide picker Tint entry** — `<Return>` now returns `"break"` so committing a hex via Enter no longer also fires the toplevel `<Return>` binding (which closed the dialog). Color is applied, dialog stays open.
  - **Reimport hidden for fonts.** `tkextrafont` registers fonts in the running Tk interpreter session-wide, so swapping the file on disk doesn't reload the glyphs until a relaunch. The reimport entry is dropped from the file-row context menu when `kind == "fonts"` — users can drop a fresh font through the + menu instead.
  - **Folder size in info panel** — `Path.stat().st_size` on a directory returns the directory entry size on Windows (~4 KB block), not the recursive content total. Walks the tree with `rglob("*")` and sums file sizes manually so a 47 KB folder actually reports 47 KB.
  - **Multi-select drag preserves selection.** `ttk.Treeview` collapses a multi-selection to a single row when the user presses on one of its members without a modifier — three selected files would drag as one. Snapshot the selection before Tk's default Button-1 handler fires; if the press lands on an already-selected row in a multi-select state, keep the original set as the drag set and restore the visual highlight on the actual drag-start (a plain click without drag still collapses, matching expected Tk UX).
  - **Font removal cleanup.** Removing a font from the picker palette OR via the Assets panel now scrubs every project reference to it, not just the file: cascade `font_defaults` entries pointing at the family are cleared, and per-widget `font_family` overrides are reset to `None` so the canvas re-renders with a fallback at the next `font_defaults_changed`. Both call paths share a new `app.core.fonts.purge_family_from_project` helper. Assets-panel removal also reads the font family from the file *before* `unlink` (PIL can't read a deleted file).
  - **`Project.clear()` resets the font cascade.** New Project used to leave the previous project's `font_defaults` + `system_fonts` in place, so a freshly created project would render every Button / Label with the prior project's chosen fonts and surface stale entries in the picker palette. `clear()` now wipes both — `_set_current_path` follows up with a `set_active_project_defaults({})` to flush the module-level cache.
  - **Font picker import emits `dirty_changed`.** Both `+ Import file...` and `+ Add system font...` now publish the event after `copy_to_assets` writes (or `system_fonts` grows) so docked / floating Assets panels refresh immediately instead of holding a stale tree until the next manual nudge.
  - **Test docs consolidated** — `docs/tests/icon_picker.md` 199 → 87 lines (15 → 5 tests), `assets_panel.md` 427 → 136 (28 → 8), `fonts.md` 355 → 109 (24 → 7). Single setup per file, grouped tests, dropped outdated steps (auto-open after creation, sounds folder, ChoiceDialog references) and the standalone harness scenario (dev-only iteration tool, not a regression test).

- **v0.0.26** (2026-04-25) — Lucide Icon Picker:
  - **`LucideIconPickerDialog`** (760×580). Layout: search bar + count, sidebar (`All` + 42 categories with counts), 6-column scrollable grid with hover + selection states, preview pane (64×64 + name + tags + tint hex entry + swatch + size dropdown), footer (Cancel / Apply). Search filters by icon name and tags across the active category (or `All`); 400-icon cap with "showing N of M — refine search" notice when "All" is unfiltered.
  - **128×128 PNG bundle** — 24×24 source replaced with 128×128 (1943 PNGs, ~8.3 MB). Higher source ⇒ sharp output at any user-selected output size; thumbnails downscale to 28 px in the grid and 64 px in the preview via PIL `LANCZOS`.
  - **Size dropdown in picker** — 24 / 32 / 48 / 64 / 96 / 128 px (default 64). Apply renders the tinted icon at this size from the 128 source instead of the previous fixed source size.
  - **Default tint `#ffffff`** — picker opens white (matches the source PNGs); user re-tints via the hex entry or the swatch (opens `ColorPickerDialog`).
  - **Project window integration** — `+ menu` and right-click `Add ▶` submenu both gain a `Lucide Icon...` entry with the `layout-list` icon, sitting above `Image...`. Smart routing — the picker's `target_dir` resolves to the right-clicked folder when present, or `assets/images/` otherwise.
  - **Image picker integration** — `+ Lucide icon...` button next to `+ Import image...` in the picker header (dialog 420 → 480 wide). On Apply, the new file lands in `assets/images/`, the picker list refreshes and auto-selects it.
  - **Sync fix — event_bus through Image picker.** `ImagePickerDialog.__init__` now takes an optional `event_bus`; `panel_commit._pick_image` passes `self.project.event_bus`. Both `_on_import` and `_on_pick_lucide` call `_notify_assets_changed()` so the docked Assets panel refreshes the moment a new file is created (previously the docked tree stayed stale until the property commit fired).
  - **Standalone test harness `tools/test_icon_picker.py`** — opens a tiny CTk window with one button that launches the picker against `tools/test_output/`, then renders a 96×96 preview + path label of whatever was picked. Lets the dialog be iterated on without needing a real `.ctkproj`. Output dir + the harness file itself are gitignored.
  - **`tools/build_lucide_categories.py` + `download-128.mjs`** — categories metadata regenerator already shipped in v0.0.25; the 128 px PNG re-render uses the existing `download.mjs` infrastructure (`sharp` + `lucide-static`) with `SIZE = 128` and `OUT_DIR = './png-icons-128'`.
  - **Test docs `docs/tests/icon_picker.md`** — 15 manual scenarios covering each entry point, search by name and tag, category filter, click + double-click select, tint commit + invalid-input recovery, color picker integration, smart routing, sync, Cancel discards, harness.
  - **`ctk-tint-color-picker` 0.3.2 → 0.3.3** — fixed bottom-edge clamp in `_center_on_parent`. The pre-map measurement was returning `1×1` so `y` could land below the visible screen / behind the taskbar; two-phase clamp + `after_idle` re-run + 80 px taskbar reserve. Library bump shipped to PyPI; `pip install --upgrade ctk-tint-color-picker` brings 0.3.3 into the builder.

- **v0.0.25** (2026-04-25) — Assets panel polish + Lucide bundle + Support links:
  - **Sounds folder removed from defaults** — `ASSET_SUBDIRS` now `("images", "fonts")`. No point shipping an empty folder users have to delete; will re-add when audio playback ships.
  - **Properties-style header redesign** — `type_bar` (HEADER_BG #2a2a2a, height 26) with folder icon + bold project name + `square-plus` "+" button; path row below in dim text. Matches Properties panel's compact look.
  - **Restructured + menu + Add ▶ submenus** — top-level: Folder / —— / Image / Font / —— / Python / Text. Folder + empty-area right-click context menus consolidated under cascading "Add ▶" submenu. Lucide icons attached to every menu entry (folder-plus, image-plus, type, file-code, file-text, pencil, trash-2, refresh-cw, square-arrow-out-up-right).
  - **Per-row icons in tree** — `_kind_icons` cache renders kind-specific glyph (folder / image / type / music / file-code / file-text / file) on every row, with two-space padding between icon and name.
  - **Empty-area click + right-click clears selection** — clicking blank tree area now deselects so the next "+ Folder" lands at root instead of inside a stale selection. Right-click also clears.
  - **Drag-and-drop multi-select move** — ghost Toplevel preview with file/folder icon + count, drop-target highlight (#26486b), invalid-drop validation (no drop into self / descendant / current parent).
  - **Open with OS hardened** — `subprocess.Popen(["explorer.exe", path])` for default verb (more reliable than `os.startfile` for UWP file associations); `.py` uses `os.startfile(path, "edit")` with idlelib fallback so double-click opens the editor instead of running the script.
  - **Removed auto-open after file creation** — creating a `.md` / `.py` no longer immediately opens it. User opens via double-click when ready.
  - **Python script template** — new `.py` files get a v0.1 disclaimer header + GitHub Issues + Buy me a Coffee links so any code shared back has feedback channels baked in.
  - **Delete folder fix** — Windows read-only attrs broke `shutil.rmtree`. Added `_force_remove_readonly` onerror handler + post-delete `folder.exists()` verification.
  - **Reveal → Open in Explorer** rename across all menus (more intuitive than "Reveal").
  - **Open assets folder in Explorer** entry on empty-area right-click menu.
  - **Sync between docked + floating Assets panels** — `dirty_changed` event emitted on `_add_asset` / `_on_new_folder` / `_create_text_file` so a font added in the floating window refreshes the docked view.
  - **About dialog: Links + Buy me a coffee + tkextrafont** — Source / Issues link row, BMC button (Lucide coffee icon, official #FFDD00 / #000000 palette), Built with list updated: `ctk-tint-color-picker` removed (user's own work), `tkextrafont` added.
  - **Lucide assets bundled** — `app/assets/lucide/categories.json` (1699 icons / 42 categories metadata), `png-icons/` (1943 PNGs at 24×24, ~3.3 MB), `LICENSE.txt` (ISC). Foundation for the upcoming Icon Picker UI.
  - **`tools/build_lucide_categories.py`** — re-runnable script that aggregates per-icon `tags` + `categories` JSONs from a Lucide source checkout into the bundled `categories.json`.
  - **README Support section** — buy-me-a-coffee link between Roadmap and License.
  - **`.github/FUNDING.yml`** — GitHub sponsor button wired to BMC.

- **v0.0.24** (2026-04-25) — Font picker UX redesign + scope literalism:
  - **Right-click row → Remove from project.** Imported fonts (file in `assets/fonts/`) get the file deleted from disk; bare `system_fonts` references just lose their entry. Cascade defaults pointing at the removed family also clear so a stale `font_defaults["CTkButton"] = "DeletedFamily"` doesn't keep widgets pointing at a missing font.
  - **Multi-size preview pane** between import buttons and palette list — `tk.Frame(height=110, pack_propagate=False)` keeps the dialog's overall height stable when swapping in a tall script font (the previous flow auto-grew, which felt jarring while clicking through families). Two sample sizes (13 / 24 px) render the live family. Editable text input on top — what the user types updates both rows immediately.
  - **Layout reordered top→bottom** — Header (Import / Add system) → Preview → Palette list → "Apply to:" segmented control → Reset / Cancel / Apply. Footer + scope packed `side="bottom"` first so they can never get pushed below the visible region by an oversize palette.
  - **Segmented scope control** — three big buttons replace the cramped radio row. Labels: "Just this widget" / "All Buttons" / "Whole project". Wired to the existing scope StringVar via a CTkSegmentedButton command.
  - **Hierarchy footer buttons** — `grid()`-based layout (column-with-spacer): Reset (70px tertiary) on the left, Cancel (90px) + Apply (140px primary) on the right with an 8px gap. Pack-based positioning was rendering Reset / Cancel cramped on the left at the dialog's actual width; grid removed the ambiguity.
  - **Dialog width 460 → 540** so the segmented control + the three action buttons breathe.
  - **Cascade dialog simplified.** Picking scope = type / all with a real family used to pop a 3-option ChoiceDialog ("Only default / All widgets / Cancel") that asked the user to re-decide a question their scope choice already answered. Now: scope is interpreted literally — "All Buttons" wipes per-button overrides, "Whole project" wipes per-widget AND per-type entries. A single info-icon `messagebox.askokcancel` warns when the new font will overwrite N existing per-widget customisations; otherwise apply silently.
  - **`tools/test_picker_buttons.py`** — throwaway debug script comparing four footer-layout strategies (pack side= / grid + spacer / place absolute / grid + width report) side-by-side. Used to settle on the grid approach above; kept in `tools/` for future layout debugging.

- **v0.0.23** (2026-04-25) — Assets panel: docked tab + free-form folders + drag-and-drop:
  - **Project panel docked alongside Properties** as a sibling tab (Properties / Assets toggle in the right pane). Floating ProjectWindow (F10) stays available for users who prefer it off to the side. Tab + window both renamed to "Assets".
  - **Compact one-row header** — bold project name + dim front-truncated path on the same line, "+" menu button on the right replacing the four-button footer. Frees the tree's vertical space.
  - **+ menu** — Image / Font / —— / Folder / Text File (.md) / Python File (.py).
  - **Free-form folder organisation.** Tree walks `assets/` recursively; user can create / rename / delete custom folders alongside the legacy `images/` / `fonts/` / `sounds/` defaults. Token resolution unchanged — `asset:relative/path/to/file.png` still resolves against the project's `assets/` root.
  - **+ New Folder** / **+ New Subfolder** at the selected location (or `assets/` root). Filename validation rejects forbidden chars + name collisions.
  - **+ New Text File (.md)** / **+ New Python File (.py)** — both prompt for a base name, default extension auto-applied, file gets a tiny starter template (`# Heading` for Markdown, module-level docstring for Python), then opens via the OS default editor for the user to start typing immediately.
  - **Right-click context menus** — full set of operations:
    - Empty area: Import Image / Font / —— / New Folder / New Text / New Python.
    - Folder row: Reveal in Explorer / —— / Import Image here / Import Font here / —— / New Subfolder / New Text / New Python / —— / Rename / Delete (recursive count + warning).
    - File row: Open / Reveal / Reimport / —— / Rename / Remove.
  - **Smart import routing** — right-click → Import Image lands in the right-clicked folder, while + menu without selection auto-routes to the legacy `images/` / `fonts/` subfolder.
  - **Double-click → OS default app** — `os.startfile` Windows / `open` macOS / `xdg-open` Linux. Folder rows still toggle expand/collapse.
  - **Reimport...** option on file rows — file picker (extension-matched) replaces the file in place; references project-wide automatically pick up the new content because the path stays the same. Useful for icon updates.
  - **Recursive picker scan** — image + font pickers now walk the whole `assets/` tree (not just the legacy fixed subfolder) so reorganised assets surface in the dialog.
  - **Multi-select + drag-and-drop** — `selectmode="extended"` (Ctrl+click / Shift+click) plus mouse-down + motion-threshold + release sequence moves files / folders between subfolders. Drop on the empty area below the tree drops into `assets/` root. Validation refuses self-drop, descendant-drop, and no-op moves to the same parent.
  - **Drag ghost** — small overrideredirect Toplevel (semi-transparent) trails the cursor during drag with a folder/file Lucide icon + "N items" caption. Replaces the previous `cursor="exchange"` system-cursor swap which felt jarring.
  - **Drop-target highlight** — legal target folder lights up in `#26486b` while the cursor is over it.
  - **Per-row icons** — Lucide leading icon by row kind: folder, image, type (font), music, file-text, file-code, file. Two-space padding between icon and label gives a comfortable visual gap.
  - **Image preview** in the info panel — selecting an image shows a thumbnail (140x140 max) below the metadata. Hidden for non-image rows.
  - **Floor-plan info panel** — selected file → name + size + image dimensions / font family / file format. Multi-select shows the placeholder.
  - **Detachable panels (universal)** captured in `ideas.md` as a major feature for later — every panel becoming both dockable and floating.

- **v0.0.22** (2026-04-25) — Font system QA pass + cascade-conflict dialog + side bugs:
  - **Cascade conflict dialog gained type-default detection.** Picking "All in project" with a real family used to silently leave per-type defaults shadowing the new value (Buttons stayed Comic Sans because `font_defaults["CTkButton"]` outranked the just-set `font_defaults["_all"]`). The dialog now lists both per-widget overrides AND per-type defaults, and "All widgets" wipes both so the new project-wide family actually applies everywhere.
  - **Load-order fix — cascade + fonts primed before widget creation.** `load_project` reads `font_defaults` / `system_fonts` from the JSON, then calls `register_project_fonts(path, root=root)` and `set_active_project_defaults(...)` BEFORE replaying `widget_added` events. Previously the workspace built widgets against an empty cascade; the editor showed default fonts even though the preview (which registers fonts at the top of `__init__`) rendered correctly. Both `_open_path` + `_on_recover_from_backup` now pass `root=self`.
  - **Picker scans the filesystem.** `list_project_fonts` no longer relies on the in-memory `_loaded_files` cache — it walks `assets/fonts/` directly, registering files lazily and falling back to `path.stem` as a family label so a font that fails Tk registration still appears in the picker. Also resolves the "some imported fonts don't show" bug.
  - **`register_font_file` stem fallback.** When tkextrafont reports `Fontfile already loaded` AND PIL can't extract the family from the .ttf metadata, we now use the file stem as a last-resort label instead of caching `""` and surfacing a "no family" warning. The previous flow lost the file from the picker entirely.
  - **Dropdown popup auto-hides on app deactivate.** `ScrollableDropdown` was creating a `-topmost` Toplevel that bled across the desktop after Alt+Tab. Added a deferred `<FocusOut>` watcher on the root that calls `focus_get()` to distinguish intra-app focus shifts (keep popup) from app-switching (hide popup).
  - **ScrollableFrame label_font** — added `font_family` to the descriptor schema (Label group) with a new `font_kwarg = "label_font"` class hook so the exporter targets the right kwarg. `_font_source` only emits `size` / `weight` / `slant` when `font_size` is in props, so a family-only label font keeps CTk's theme defaults.
  - **ComboBox + OptionMenu popup items inherit parent font.** `ScrollableDropdown` now accepts a `font` parameter, applies it to every row CTkButton, and the descriptors thread `widget._font` through both `create_widget` and `apply_state`. Exporter emits `font=<var>.cget("font")` so the dropdown matches the field after construction.
  - **CTkTabview tab font.** Added `font_family` to the descriptor + `_apply_tab_font` post-construction step that calls `widget._segmented_button.configure(font=CTkFont(family=...))` (CTkTabview's `__init__` has no `font` kwarg). New `font_kwarg = None` sentinel tells the exporter to skip the constructor font emission; `export_state` writes the post-construction `_segmented_button.configure(font=...)` line.
  - **CTkLabel italic clip.** Last glyph of script / italic fonts was clipping at the inner label's right edge — Tk measures glyph advance widths and undercounts the slant tail. Configured `widget._label.configure(padx=4)` in `apply_state` (and mirrored in `export_state`); 4px is invisible on upright fonts and rescues the slant overhang on italics.
  - **CTkSegmentedButton + CTkOptionMenu width fix.** Both descriptors set `dynamic_resizing=False` at runtime, but the kwarg was never persisted to `properties` so the exporter dropped it — exported apps fell back to CTk's grow-to-content default and ignored the configured width. Added `export_kwarg_overrides` returning `dynamic_resizing=False`, plus an exporter loop that fans out override-only keys (those not in `properties`) into the constructor kwarg list.
  - **`ChoiceDialog`** — new 3-button helper in `dialogs.py` for cascade-edit prompts. Used by `_pick_font` for the "Apply font to all widgets?" choice (Only default / All widgets / Cancel).
  - **Side fix — New Project default save dir.** After saving a project, opening File → New no longer suggests the previous project's folder as `Save to`; walks one extra level up to the parent directory the user originally chose.

- **v0.0.21** (2026-04-25) — Custom font system (Phase 1–4 + exporter integration):
  - **`tkextrafont 0.6.3`** added to dependencies — registers .ttf / .otf with the running Tk interpreter so `CTkFont(family=...)` resolves bundled families.
  - **`app/core/fonts.py`** — `register_font_file` / `register_project_fonts` / `list_project_fonts` / `list_system_families` / `resolve_system_font_path` (Windows registry lookup) / `resolve_effective_family` cascade helper. Graceful fallback when tkextrafont can't import. Handles tkextrafont's "already loaded" by reading family from .ttf metadata via PIL.
  - **`font_family` schema property** added to 10 descriptors (Button / Label / Entry / Textbox / CheckBox / RadioButton / Switch / ComboBox / OptionMenu / SegmentedButton). Default `None` → use Tk default. transform_properties resolves via cascade.
  - **`app/ui/font_picker_dialog.py`** — main project-palette picker (imported .ttf + added system fonts) with `+ Import file` and `+ Add system font` buttons. Help icon (`?`) with explainer tooltip. Scope selector: This widget / All [Type] / All in project.
  - **`SystemFontPickerDialog`** secondary dialog — full OS font list with search box. Add → resolves via Windows registry → copies .ttf into `assets/fonts/` so the project stays portable. Falls back to a bare `system_fonts` ref entry if the file can't be located.
  - **`FontEditor`** overlay (Properties panel) — Image-style ⋯ + ✕ buttons. Click ⋯ opens picker; click ✕ clears to default.
  - **Cascade defaults** stored in `project.font_defaults` (`_all` key + per-type-name keys). Save/load round-trips via top-level `font_defaults` and `system_fonts` keys in the .ctkproj JSON. `font_defaults_changed` event triggers a workspace reapply that re-runs each widget's transform.
  - **Bug fix — zoom override**: `ZoomController._build_scaled_font` was creating a CTkFont without `family=`, clobbering the descriptor's resolved family on every property edit. Now reads the existing `widget._font.cget("family")` and preserves it.
  - **Bug fix — preview text fallback**: Georgian / CJK glyphs in the row preview text forced Tk to use a fallback font for Latin-only families, making every row look identical. Switched to `"AaBb 123"` and filtered out `@`-prefixed CJK vertical-text variants.
  - **Bug fix — project_window crash**: stale `dirty_changed` subscriber survived after the floating Project window closed; refresh now early-returns when the panel doesn't exist anymore.
  - **Code exporter** — `_project_uses_custom_fonts` detector triggers a `_register_project_fonts(root)` helper at the top of the generated `.py`, called from each main-class `__init__` so widget construction can resolve the bundled families. `_font_source` now takes the resolved family and emits `family='...'` as the first CTkFont kwarg. Helper soft-imports tkextrafont so generated apps still run when the dependency isn't installed.

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
