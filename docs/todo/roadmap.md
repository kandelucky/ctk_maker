# Roadmap — დაგეგმილი ფაზები

> Committed სამუშაო. რიგი განსაზღვრულია ზემოდან ქვემოთ.

---

## 🚧 Active — Area 4 Commands QA pass

- [ ] Area 4 — Commands (undo/redo): every mutation reversible, coalescing — `docs/testing/commands.md` (0/43)
- [ ] Area 5 — Project lifecycle: save/load/export round-trip (0/44)
- [ ] Area 6 — Multi-document: dialogs, chrome, cross-doc drag, accent color, z-order (0/54)
- [ ] Area 7 — Widgets: 14+1 descriptors per-widget sanity (0/41)
- [ ] Area 8 — Inspectors & Dialogs: Object Tree, History, menubar/toolbar, modals, Window Settings (0/103)

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

## Phase 5 remaining — Window Settings

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
