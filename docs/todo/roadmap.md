# Roadmap — დაგეგმილი ფაზები

> Committed სამუშაო. რიგი განსაზღვრულია ზემოდან ქვემოთ.

---

## 🚧 Active — QA rounds

- [x] Area 4 — Commands (undo/redo): 42/43 ✅
- [x] Area 5 — Project lifecycle: 41/44 ✅
- [x] Area 6 — Multi-document: 54/54 ✅
- [ ] Area 7 — Widgets: 19 palette entries, 115-item per-widget sweep — `docs/testing/widgets.md` (0/115)
- [ ] Area 8 — Inspectors & Dialogs: Object Tree, History, menubar/toolbar, modals, Window Settings (0/103)

---

## Multi-document workspace UX

- [ ] **Hide / show individual dialogs in workspace** — per-document visibility toggle in the chrome strip (eye icon or minimize button). Hidden dialogs stay in the project / Object Tree but are collapsed off-canvas. Useful when working on one window without the others cluttering the viewport. Pairs with the existing `node.visible` toggle logic; needs a document-level visibility flag in `ProjectDocument`.

- [ ] **Project files / assets browser panel** — 4th sidebar tab showing all files referenced by the project (images, fonts, any future asset types). Thumbnails + path + "Locate missing file" for broken refs. Drag from panel → canvas sets the `image` property. Foundation for the portable-assets system.

---

## Dedicated dialogs / windows

Three windows currently delegate to native OS dialogs (or run silently in the background) and would benefit from a richer in-builder UI.

- [ ] **Export dialog** — replace the bare `asksaveasfilename` File → Export step with a real dialog: target file path, scope (whole project vs active document), include `assets/` toggle (after the asset system lands), preview pane showing first N lines of generated code, "Open file after export" checkbox. Same dialog reused by File → Export and the per-document chrome Export icon.

- [ ] **Run Python Script window** — today's Run Script just spawns `subprocess.Popen` and the user has zero feedback if the script crashes or prints. Wrap the launch in a small window: title bar with the script path, stdout / stderr captured into a scrolling text panel, exit code shown when the process ends, Stop button to kill the subprocess. Optionally support running `.ctkproj` directly (regenerate-and-run path from `ideas.md`).

- [ ] **Settings / Preferences window** — global settings (`~/.ctk_visual_builder/settings.json`) currently have no UI; the "Reset Dismissed Warnings" item is the only entry exposed. Build a real Preferences dialog: appearance mode, default font / size, default project location, recent-project list cap, run-script defaults, dismissed-warnings list with per-item re-enable, autosave interval (after the autosave layer lands), color picker presets management.

---

## Portable images — assets system

Image widgets currently export with **absolute filesystem paths** baked into the generated `.py`. Projects break the moment the user:
- Moves the project folder
- Sends the `.py` to another machine
- Renames the source image on disk

Target fix (committed, must ship before v1.0):

- [ ] `assets/` folder alongside the `.ctkproj` file, auto-populated with every referenced image on save (copy-on-first-reference, deduped by SHA).
- [ ] Widget `image` property stores `asset:<asset_id>` tokens instead of raw paths; the builder resolves tokens through `project.assets` at render time.
- [ ] Exporter copies every used asset into `assets/` beside the generated `.py` and rewrites paths to relative (`Image.open("assets/<name>")`).
- [ ] Load migration: legacy projects with absolute paths are moved into `assets/` on first save; tokens replace the raw paths.
- [ ] Asset model: `project.assets: dict[asset_id → AssetEntry]` with `(relative_path, sha256, last_modified)`.
- [ ] Missing asset on load — graceful degradation (placeholder + entry in observations).

**Later**: Assets panel (4th sidebar tab — thumbnails, drag-to-canvas, drag-to-property, Import…). Drag-from-Explorer needs `tkinterdnd2`. That panel is a UX layer on top of the asset model, not a hard requirement for the portability fix.

---

## Phase 7 — Select / Edit tool separation (remaining)

- [ ] Marquee selection — drag on empty canvas draws a rectangle; widgets inside get added to selection
- [ ] Group copy / paste / duplicate / delete — operate on the full selection set, not just primary
- [ ] Cursor swap per mode (distinct icons, keyboard shortcut)
- [ ] Remember last mode across sessions
- [ ] Benchmark: selection time Select vs Edit with 100-widget project

---

## Phase 7 — Polish & Pro Features

- [ ] Marquee selection (drag on empty canvas area)
- [ ] Snap-to-grid (8px grid)
- [ ] Alignment guides (snap to other widgets' edges/centers)
- [~] Copy / Paste / Cut (Ctrl+C / V / X) — done in Object Tree; pending: canvas bindings, Cut, OS clipboard
- [ ] Z-order management (beyond Bring/Send)
- [ ] Group / Ungroup widgets
- [ ] "Folder" builder-only grouping node (emits nothing in exported `.py`)
- [ ] Asset manager — copy images into project `assets/` folder for portability
- [ ] Assets library panel — user-scoped fonts/images/icons, dropdowns pull from library

---

## Phase 6.x — Widgets remaining

### CTkScrollableFrame — container behavior

Children dropped into CTkScrollableFrame via Object Tree appear in the model but are invisible on canvas. Root cause: CTkScrollableFrame embeds a tk.Canvas whose scroll region is only updated via `<Configure>` events on `self`; `place()` children don't trigger that event, so the scrollable canvas never "sees" them.

Fix path:
- After reparenting a child into ScrollableFrame, manually update `_parent_canvas` scroll region: call `widget._parent_canvas.configure(scrollregion=widget.bbox("all"))` or similar.
- Or bind `<Configure>` on the inner scrollable frame to always sync scroll region.
- May also need workspace to re-lift the inner child above the canvas layer.

Simpler alternative: force ScrollableFrame children to use `pack()` or `grid()` (not `place()`) so CTk's geometry propagation updates the canvas naturally.

### CTkTabview + CTkScrollableFrame nesting

Drop widgets into specific tabs / inside scrollable frame. Shared container-nesting story for composite widgets.

**Missing in builder:**
- "Active tab" context during drop → `tabview.get()` becomes parent
- Per-child `parent_slot` (tab name) in WidgetNode, stable across save/load/reparent
- Runtime rendering: `tabview.tab(node.parent_slot)` as master
- `is_container=True` flip once above lands
- Exporter two-pass (assign var names, then emit) so `CTkLabel(tabview_1.tab("Tab 1"), ...)` works
- Tab rename propagation (old→new name tracking, currently diff treats as delete+add, orphans children)

Same story for CTkScrollableFrame. Design once, apply to both.

### Phase 6.7 — Layout manager options (detail-level)

- [ ] place options in Layout section (relx, rely, anchor)
- [ ] pack options (side, anchor, fill, expand, padx, pady)
- [ ] grid options (rowspan, columnspan — currently only row/column/sticky)
- [ ] Visual indicator on workspace (which manager is in use — done via badges, verify complete)
- [ ] Code exporter respects full layout_type options

### Layout-in-layout nesting

Currently blocked: Vertical/Horizontal/Grid Layout can't be dropped into another layout. Qt Designer allows freely. Need:
- Stop bbox-caching for nested grid targets
- Recursively propagate geometry manager swaps
- Fix z-order when inner layouts' canvas items stack above outer chrome
- Widen `_find_container_at` depth preference to pick deepest layout

Worth a dedicated mini-phase after current refactor round.

---

## Phase 4 — Undo / Redo (status check)

> History already implemented (Ctrl+Z, F9 history panel, all mutations tracked). Verify complete, remove section if so.

- [x] Command base class + history stacks
- [x] AddWidgetCommand, DeleteWidgetCommand, MoveWidgetCommand, ResizeWidgetCommand, ChangePropertyCommand
- [x] Ctrl+Z / Ctrl+Y shortcuts + toolbar buttons

### Auto-grow grid remaining

- [ ] Undo unity for layout swap — layout_type + N grid_row/column updates wrapped in one compound command
- [ ] Load migration — legacy grid_row/col collisions don't trigger distribute pass on load

### History panel UX

- [ ] **Better entry labels** — current labels are generic ("Change Property", "Add Widget"). Include prop name + value diff ("Change fg_color: #1f6aa5 → #ff0000"), widget type ("Add CTkButton"), count for bulk ("Delete 3 widgets"). Pulls the description from the command's existing `label` field where set; audit each Command subclass for useful labels.
- [ ] **Click entry → jump to that history point (multi-step undo)** — clicking a History row should replay undo (or redo) multiple steps until that entry is current. Today Ctrl+Z is step-by-step only; this matches Photoshop/Figma's history panel UX. Implementation: `history.jump_to(index)` loops undo/redo N times with `suspend_events_until_end` to avoid intermediate selection/render thrash.

---

## Phase 0.5 remaining — Property Editor

- [ ] Reset-to-default button per property
- [ ] Tooltip / hint when hovering over property labels
- [ ] Collapsible property groups
- [ ] Numeric editor: arrow keys (↑/↓ = ±1, Shift+↑/↓ = ±10)
- [ ] **Font editor** — dedicated `font` editor type in v2 registry: system families picker (`tkinter.font.families()`), search, live preview, bold/italic/underline/strike. Covers Area 3 test #11.
- [ ] **Resize handles geometry bounds** — drag-resize via canvas handles bypasses the `_commit_prop` clamp (typed values only). Apply `min(w, container_w - x)` at end of resize-drag commit before `ChangePropertyCommand` push.

---

## Phase 2.x — Properties panel rewrite remaining

- [ ] **Retest stale drag** after v2 panel — verify "widget follows mouse after tree click" no longer reproduces
- [ ] **`panel.py` split** (done for schema + commit; `_populate_schema` filtering internals + API asymmetry unification still open — low priority)
- [ ] **`disabled_when` / `hidden_when` perf** — dep-map via `TrackingDict` so lambdas re-evaluate on changed props only (O(1) vs O(N))
- [ ] **Surgical rebuild on `layout_type` change** — currently full panel rebuild

---

## Phase 3 remaining — Widget docs + perf

- [ ] Per-widget docs page under `docs/widgets/ctk_*.md` for remaining descriptors
- [ ] `disabled_when` perf check with measured drag-time overhead

---

## Project file safety — backups / autosave / crash recovery

Currently a `.ctkproj` save is a plain overwrite — if the write is interrupted (crash / power loss) or the file is hand-edited into corruption, the project is gone. The "try a backup" message in the damaged-file dialog is currently a polite fiction because the builder never makes one.

Four layers, ordered by effort:

- [x] **`.bak` on save** (minimal viable, v0.0.18.1) — before writing the new JSON, atomically rotates the existing file to `<name>.ctkproj.bak` via `os.replace`. One generation kept; next save overwrites the `.bak`. Damaged-project dialog now points at the `.bak` sibling for recovery instead of the prior "polite fiction" message.
- [ ] **Rotated backups** — keep `<name>.ctkproj.bak1` / `.bak2` / `.bak3` (ring buffer, newest first). Slightly more disk, survives two bad saves in a row.
- [x] **Autosave** (v0.0.18.2) — every 5 minutes while dirty AND with a saved path, `AutosaveController` writes `<name>.ctkproj.autosave` next to the real file (atomic via `.tmp` + `os.replace`). Cleared on explicit Save and on the user's "Discard" answer to the unsaved-changes prompt. On open, the loader compares mtimes and offers to restore if `.autosave` is newer than `.ctkproj`. Untitled projects (no path) skipped — Phase 2 will spool them to `~/.ctk_visual_builder/autosave/`.
- [ ] **Crash-recovery session** — detect when the builder was killed without closing the project cleanly (lock file in `~/.ctk_visual_builder/`). On next launch, if a lock file is orphaned, offer the autosave as a recovery option.
- [ ] **Settings folder rename `~/.ctk_visual_builder/` → `~/.ctkmaker/`** — display name flipped to CTkMaker in v0.0.18.3 but the per-user config dir kept its old name to avoid losing existing `settings.json` / `recent.json` / future autosave spool. One-shot migration: on first launch under the new name, if `~/.ctkmaker/` doesn't exist but `~/.ctk_visual_builder/` does, copy the dir over and leave a `.migrated` marker behind so we don't keep migrating. Schedule for the same release that introduces the untitled-autosave spool dir, since both touch the same root folder.

- [ ] **Untitled-project autosave (Autosave Phase 2)** — current autosave (v0.0.18.2) is path-anchored: a brand-new project that has never been saved gets no `.autosave` file because there's no `.ctkproj` next to which to write it. A 4-hour edit on an untitled workspace is therefore lost on crash. Fix: spool untitled sessions to `~/.ctk_visual_builder/autosave/<session_id>.ctkproj.autosave` with a sidecar metadata file (start time, last edit time). On startup, scan the dir; if any orphaned sessions exist, present a "Recover untitled session?" dialog at the welcome screen. Discard / restore / preview options.

Layer 1 (.bak) shipped v0.0.18.1; Layer 3 (autosave for saved projects) shipped v0.0.18.2. Layers 2 (rotated bak), 4 (crash-recovery lock file), and Autosave Phase 2 (untitled spool) deferred.

- [ ] `appearance_mode` (system / light / dark) — currently global Settings only
- [ ] Window icon (`iconbitmap` / `iconphoto`) — Phase 8-adjacent

---

## Phase 9 — Distribution & Release

> **Priority**: before Phase 8 (Advanced). Installers are prerequisite for users.

### Phase 9.6 Naming ✅

Final name: **CTkMaker** (2026-04-20). Pending: availability check (PyPI, GitHub, domain, social), reserve + rename.

### Phase 9.1 — PyPI release

- [ ] Decide final package name (availability check first)
- [ ] `pyproject.toml` metadata + entry point
- [ ] Version single-source at `app/__version__.py`
- [ ] TestPyPI smoke test
- [ ] Publish to PyPI
- [ ] README install section update

### Phase 9.2 — Windows installer

- [ ] PyInstaller build (one-folder for startup + AV)
- [ ] Bundle `app/assets/icons/` via `--add-data`
- [ ] Inno Setup installer — shortcut, `.ctkproj` file assoc, uninstaller
- [ ] Code signing cert (EV preferred, ~$300/yr)
- [ ] Test on clean Win 10 + 11 VM

### Phase 9.3 — macOS installer

- [ ] PyInstaller `.app` bundle + Info.plist
- [ ] Universal build (arm64 + x86_64)
- [ ] create-dmg script
- [ ] Apple Developer enrollment ($99/yr)
- [ ] codesign + notarytool staple

### Phase 9.4 — CI/CD

- [ ] GitHub Actions `on: push tags v*` → parallel Win + Mac builds
- [ ] Secrets for signing + PyPI token
- [ ] Release notes auto-generated

### Phase 9.5 — Auto-updater

- [ ] Help → Check for Updates menu
- [ ] GitHub Releases API poll on startup (opt-out)
- [ ] Win: download + launch installer + exit
- [ ] Mac: download DMG + open + prompt drag-to-Applications

### Phase 9.7 — Landing page + docs site

- [ ] Static site (Astro / Next / HTML)
- [ ] Sections: hero, feature grid, download buttons, comparison, docs, GitHub
- [ ] GitHub Pages or Netlify, custom domain
- [ ] MkDocs or Docusaurus for docs

### Phase 9.8 — Launch marketing

- [ ] Demo GIF (30 sec)
- [ ] Short demo video (2 min)
- [ ] Product Hunt launch — midweek
- [ ] Reddit: r/Python (Saturday Showcase), r/learnpython, r/CustomTkinter
- [ ] Hacker News Show HN — weekend
- [ ] Blog post: "Why I built another CTk visual builder"

### Phase 9.9 — Community infra

- [ ] CONTRIBUTING.md
- [ ] GitHub issue templates
- [ ] Discussions enabled
- [ ] "Getting started in 5 min" tutorial
- [ ] Example projects — 3–5 bundled `.ctkproj` files (login form, settings dialog, dashboard) opened via File → Open Example; shows the builder's full capability at first launch
- [ ] GIF tutorials — screen-recorded walkthroughs per feature (drop widget, edit properties, export + run); embedded in docs site and README; 10–30 sec each
