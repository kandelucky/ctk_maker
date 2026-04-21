# Done — შესრულებული ფაზები

> არქივი. თითოეული ფაზა ერთხაზიანი შემაჯამებელით. სრული დეტალები git history-ში.

---

## 2026-04 — Area QA passes + refactors

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
