# Testing Cycle

Area-by-area QA pass toward v1.0. Each area runs one cycle:

1. **Test** — walk the checklist, log bugs + surprises
2. **Refactor** — apply structural cleanups uncovered during testing
3. **Optimize** — measure, then fix hot spots

Work one area top-to-bottom before moving on. Commit at the end of each area's cycle.

## Progress

Overall: **38 / 409** tests passed (9%)

| # | Area | File | Focus | Progress |
|---|------|------|-------|----------|
| 1 | Workspace core | [workspace.md](workspace.md) | palette drop, drag, resize, select, nudge | 38 / 38 ✅ |
| 2 | Layout managers | [layout.md](layout.md) | place / vbox / hbox / grid + nested + reparent | 0 / 44 |
| 3 | Properties panel | [properties.md](properties.md) | editors, disabled/hidden_when, drag-scrub | 0 / 42 |
| 4 | Commands (undo/redo) | [commands.md](commands.md) | every mutation reversible, coalescing | 0 / 43 |
| 5 | Project lifecycle | [project.md](project.md) | save / load / export round-trip | 0 / 44 |
| 6 | Multi-document | [multi_document.md](multi_document.md) | dialogs, chrome, cross-doc drag, accent color, z-order | 0 / 54 |
| 7 | Widgets | [widgets.md](widgets.md) | 14+1 descriptors, per-widget sanity | 0 / 41 |
| 8 | Inspectors & Dialogs | [inspectors_dialogs.md](inspectors_dialogs.md) | Object Tree, History, menubar / toolbar / shortcuts, modals, Window Settings | 0 / 103 |

**Current area:** Area 1 complete ✅ — all 38 tests passed. Next: Area 2 — Layout managers.
**Bugs found:** 31 (WS-1 outside-drop, WS-2 click-stack, WS-3 snap-back, WS-4 container extract-only, WS-5 active-doc follow, WS-6 drag ghost, WS-7 drill-down select, WS-8 grid-cell handle follow, WS-9 chrome ghost, WS-10 locked delete silent, WS-11 tree bypassed lock, WS-12 locked chrome tracked drag, WS-13 tree reparent strange position, WS-14 tree reparent undo missing, WS-15 multi-delete single-only, WS-16 cross-doc delete undo, WS-17 cross-doc add redo, WS-18 cross-doc drag undo, WS-19 accent color collision, WS-20 left-click empty doc, WS-21 window settings in select mode, WS-22 document move undo left widgets behind, WS-23 canvas Ctrl+C/V missing, WS-24 Georgian-layout clipboard shortcut, WS-25 paste cascade stacked, WS-26 frame paste strange position, WS-27 tree reorder redo broken, WS-28 canvas transparent fallback mismatch [deferred], WS-29 image small-inside-dark-frame [deferred], WS-30 doc drag hide-mode un-hidden each motion, WS-31 cross-doc drag snap-back regression)
**Refactors done:** 0
**Optimizations applied:** 0

## Legend

- `- [ ]` pending, `- [x]` passed, `- [!]` bug found (link to note at bottom)
- **Refactor:** structural change that makes future work cleaner
- **Optimize:** measured slowdown with a proposed fix
