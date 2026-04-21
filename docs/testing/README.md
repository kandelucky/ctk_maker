# Testing Cycle

Area-by-area QA pass toward v1.0. Each area runs one cycle:

1. **Test** — walk the checklist, log bugs + surprises
2. **Refactor** — apply structural cleanups uncovered during testing
3. **Optimize** — measure, then fix hot spots

Work one area top-to-bottom before moving on. Commit at the end of each area's cycle.

## Progress

Overall: **162 / 409** tests passed (40%)

| #   | Area                 | File                                           | Focus                                                                        | Progress  |
| --- | -------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------- | --------- |
| 1   | Workspace core       | [workspace.md](workspace.md)                   | palette drop, drag, resize, select, nudge                                    | 38 / 38 ✅ |
| 2   | Layout managers      | [layout.md](layout.md)                         | place / vbox / hbox / grid + nested + reparent                               | 44 / 44 ✅ |
| 3   | Properties panel     | [properties.md](properties.md)                 | editors, disabled/hidden_when, drag-scrub                                    | 38 / 42 ✅ |
| 4   | Commands (undo/redo) | [commands.md](commands.md)                     | every mutation reversible, coalescing                                        | 42 / 43 ✅ |
| 5   | Project lifecycle    | [project.md](project.md)                       | save / load / export round-trip                                              | 0 / 44    |
| 6   | Multi-document       | [multi_document.md](multi_document.md)         | dialogs, chrome, cross-doc drag, accent color, z-order                       | 0 / 54    |
| 7   | Widgets              | [widgets.md](widgets.md)                       | 14+1 descriptors, per-widget sanity                                          | 0 / 41    |
| 8   | Inspectors & Dialogs | [inspectors_dialogs.md](inspectors_dialogs.md) | Object Tree, History, menubar / toolbar / shortcuts, modals, Window Settings | 0 / 103   |

**Current area:** Area 4 complete ✅ — 42/43 passed (click-to-jump in History panel pending → roadmap). Next: Area 5 — Project lifecycle.
**Bugs found:** 50 (+ C4-1 Ctrl+Z auto-repeat spam)
**Refactors done:** 1 (v0.0.15.12 — panel.py → SchemaMixin + CommitMixin split, 1378 → 682 lines)
**Optimizations applied:** 0

## Legend

- `- [ ]` pending, `- [x]` passed, `- [!]` bug found (link to note at bottom)
- **Refactor:** structural change that makes future work cleaner
- **Optimize:** measured slowdown with a proposed fix
