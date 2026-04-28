# Version history

Visual snapshots of CTkMaker across releases. Screenshots only on the milestones that introduced something visibly new.

| Version | Screenshot | Highlights |
|---------|-----------|------------|
| **v1.0.6** | [![v1.0.6](v1.0.6.png)](v1.0.6.png) | In-app **Bug / Feature reporter** — Help menu + toolbar button open a structured form that submits via GitHub Issue Form template URL or markdown export. Plus a hotfix to v1.0.5's group selection (Ctrl+Click toggles whole group, orange bbox follows during drag). |
| **v1.0.5** | _no screenshot_ | **Group / Ungroup widgets** (Ctrl+G / Ctrl+Shift+G). Click a member targets the whole group, fast follow-up drills to one, drag carries the group as one. Object Tree shows a virtual `◆ Group (n)` parent row. |
| **v1.0.4** | _no screenshot_ | **Marquee selection + smart snap guides.** Drag-rect on empty canvas multi-selects (Photoshop touch mode). While dragging a widget, cyan guides snap edges / centre to siblings + container; Alt bypasses. |
| **v1.0.3** | [![v1.0.3](v1.0.3.png)](v1.0.3.png) | **Alignment + distribution toolbar** — 6 align (L/C/R + T/M/B) + 2 distribute (H/V). Auto-detects intent: 1 widget aligns to its container, multiple widgets align to each other. |
| **v1.0.2** | _no screenshot_ | **Multi-page projects** (Unity-style workspace). One project folder, multiple Page designs sharing a single asset pool. Save As gains 3 scopes; Export ships only used assets per page. |
| **v1.0.1** | [![v1.0.1](v1.0.1.png)](v1.0.1.png) | **Card widget** with embedded image (anchor / tint / padding / preserve-aspect) plus a bug sweep across drop coords, hidden frames, eye-icon cascade, and Save As asset copy. |
| **v1.0.0** | _no screenshot_ | **First stable release.** Visual canvas, 19-widget palette, multi-document workspace, layout managers (place / vbox / hbox / grid), asset system, code export, undo/redo with History panel. |
| **v0.0.15.x** | _no screenshot_ | **Area 1 workspace QA + perf refactors** across 9 patches — selection chrome z-order, frame-pool for multi-select draw, drag controller decomposition, ghost-mode for large group drags, cross-doc reparent undo. |
| **v0.0.14** | [![v0.0.14](v0.0.14.png)](v0.0.14.png) | **Grid place-based centring + workspace refactor.** CTkFrame's rounded canvas broke tk's native `.grid()` math; children now render via hand-computed `.place()` coords. WidgetLifecycle extracted from workspace core. |
| **v0.0.13** | _no screenshot_ | **Grid WYSIWYG + drag-to-cell.** Children render into real cells; drag snaps to cell under cursor with light-blue dashed outline. Runtime export emits matching `grid_propagate(False)` + weight calls. |
| **v0.0.12** | _no screenshot_ | **vbox / hbox WYSIWYG + Layout presets.** Children render with real `pack()` on canvas — builder preview matches exported runtime. Palette gains 4 layout presets. workspace.py split into a 6-file package. |
| **v0.0.11** | _no screenshot_ | **pack split into vbox / hbox.** Direction now lives on the parent (Qt Designer convention). Properties dropdown renders Lucide icons per option. Legacy `.ctkproj` files auto-migrate. |
| **v0.0.10** | _no screenshot_ | **Layout managers (stage 1 + 2).** Containers gain `layout_type` ∈ `place / pack / grid`; properties panel shows parent-driven children rows; code exporter swaps `.place()` per parent. |
| **v0.0.9** | [![v0.0.9](v0.0.9.png)](v0.0.9.png) | **Multi-document canvas.** One `.ctkproj` holds Main Window + N Dialogs, all visible together. Per-document chrome with drag, active highlight, palette drop targeting, AddDialog preset picker. |
| **v0.0.8** | [![v0.0.8](v0.0.8.png)](v0.0.8.png) | **Phase 3 widgets + Undo / Redo.** 13 widgets land (Entry, CheckBox, ComboBox, …). Full command-based history with the History panel (F9). |
| **v0.0.7** | [![v0.0.7](v0.0.7.png)](v0.0.7.png) | **Properties panel v2 rewrite** — ttk.Treeview backbone, flicker-free overlays, modular editor registry. |
| **v0.0.6** | [![v0.0.6](v0.0.6.png)](v0.0.6.png) | First widgets — CTkLabel / CTkFrame, workspace canvas, startup dialog. |
