# Testing Cycle

Area-by-area QA pass toward v1.0. Each area runs one cycle:

1. **Test** — walk the checklist, log bugs + surprises
2. **Refactor** — apply structural cleanups uncovered during testing
3. **Optimize** — measure, then fix hot spots

Work one area top-to-bottom before moving on. Commit at the end of each area's cycle.

## Progress

Overall: **471 / 483** tests passed (97%)

| #   | Area                 | File                                           | Focus                                                                        | Progress     |
| --- | -------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------- | ------------ |
| 1   | Workspace core       | [workspace.md](workspace.md)                   | palette drop, drag, resize, select, nudge                                    | 38 / 38 ✅    |
| 2   | Layout managers      | [layout.md](layout.md)                         | place / vbox / hbox / grid + nested + reparent                               | 44 / 44 ✅    |
| 3   | Properties panel     | [properties.md](properties.md)                 | editors, disabled/hidden_when, drag-scrub                                    | 38 / 42 ✅    |
| 4   | Commands (undo/redo) | [commands.md](commands.md)                     | every mutation reversible, coalescing                                        | 42 / 43 ✅    |
| 5   | Project lifecycle    | [project.md](project.md)                       | save / load / export round-trip                                              | 40 / 44 ✅    |
| 6   | Multi-document       | [multi_document.md](multi_document.md)         | dialogs, chrome, cross-doc drag, accent color, z-order                       | 54 / 54 ✅    |
| 7   | Widgets              | [widgets.md](widgets.md)                       | 19 palette entries — per-widget sanity + surprises                           | 115 / 115 ✅  |
| 8   | Inspectors & Dialogs | [inspectors_dialogs.md](inspectors_dialogs.md) | Object Tree, History, menubar / toolbar / shortcuts, modals, Window Settings | 100 / 103 ✅  |

**Current area:** Area 8 complete ✅ — 100/103 passed (3 theme-toggle deferred to bugs.md). Next: pre-v1.0 critical features.
**Bugs found:** 80 (8 new in Area 8 — all fixed; 1 deferred: theme toggle; 1 OS limitation: menu border)
**Refactors done:** 14
- v0.0.15.12 — panel.py → SchemaMixin + CommitMixin split, 1378 → 682 lines
- v0.0.15.17 — main_window.py → ShortcutsMixin + MenuMixin split, 1234 → 753 lines
- v0.0.15.13–15 — Widget descriptors: text_position, text_hover, disabled visuals
- v0.0.15.16–18 — Segment editors: SegmentValuesDialog, segment_values/segment_initial ptype
- v0.0.15.19–21 — Export engine: radio group, text-align helper, clipboard helper, hover helper
- v0.0.15.22–24 — Widget Inspector + idempotent workspace bind + Image/ScrollableFrame QA fixes
- v0.0.15.25–26 — Object Tree UX: inline rename, type initials, History docked + click-to-jump, sidebar toggle headers
- v0.0.15.27–28 — File menu polish (New Untitled), Widget menu + palette regrouped
- v0.0.15.29 — Form menu redesign (Preview Active, All Forms submenu, Move Up/Down, Form Settings)
- v0.0.15.30 — About dialog with library links
- v0.0.15.31 — Workspace bar (Preview/Preview Active buttons, All Forms dropdown)
- v0.0.15.32 — Shortcuts overhaul (Ctrl+D/X/I/P/M/A/Shift+I, Georgian fallback, README table)
**Optimizations applied:** 0

## Legend

- `- [ ]` pending, `- [x]` passed, `- [!]` bug found (link to note at bottom)
- **Refactor:** structural change that makes future work cleaner
- **Optimize:** measured slowdown with a proposed fix
