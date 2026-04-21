# Reference — საცნობარო მასალა

> Qt Designer feature map, Lucide icons, design direction notes.

---

## Qt Designer (classic)

**Design direction**: we are cloning Qt Designer's widget-based UX for CustomTkinter. Qt Designer is the 20-year-old battle-tested UI designer for Qt widgets — same mental model as ours (place widget → edit properties → export code). We explicitly **NOT** cloning Qt Design Studio (QML-based, declarative, states/timelines — overkill for CTk which is imperative).

Docs: https://doc.qt.io/qt-6/qtdesigner-manual.html

### Qt Designer features mapped to our phases

- [x] **Three-panel layout** (Widget Box / Workspace / Property Editor) — Phase 0
- [x] **Drag-to-add from palette** — Phase 1
- [x] **Click-to-select with resize handles** — Phase 1
- [x] **Property editor with grouped sections** — Phase 0.5
- [x] **Toolbar** (New / Open / Save / Preview / Export) — Phase 2
- [x] **Object Inspector** (hierarchical widget tree panel) — Phase 6.6
- [x] **Layout managers** (pack / grid / place) with visual indicator — Phase 6
- [x] **Preview mode** — separate window running the generated app — Phase 2
- [x] **Form layouts** (sticky in grid) — Phase 6
- [ ] **Collapsible property groups** — Phase 0.5 remaining
- [ ] **Alignment tools** (align left/right/center when multi-selection) — Phase 7
- [ ] **Tab order editor** — Phase 8
- [ ] **Snap-to-grid + alignment guides** — Phase 7
- [ ] **Signal/Slot editor** → our "event handlers" — Phase 8
- [ ] **Resource editor** (assets management) — Phase 7

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

## Icon library: Lucide

**Library**: https://lucide.dev — MIT, 1500+ outline icons.

**Workflow**: Claude lists the icons needed for each feature. User manually downloads PNGs from lucide.dev. Claude does not download.

**Fixed parameters** (set 2026-04-13 on first icon selection — all future icons must match):

- **Render size**: **16 × 16** px
- **Stroke width**: **2** (Lucide default)
- **Color**: **#888888** (baked into PNG — dark theme subtle gray, matches group-header text color)
- **Format**: PNG with RGBA alpha channel

Helper: `app/ui/icons.py` → `load_icon(name, size=16) -> CTkImage`. Cached after first load.

Currently: 1943 PNGs downloaded via `tools/download.mjs` (Node + sharp) at 24×24 white. Tinting system recolors on demand via PIL `Image.composite` on alpha mask.

---

## Official CTk reference bundled

`tools/fetch_ctk_reference.py` shallow-clones TomSchimansky/CustomTkinter and copies `examples/` + `test/manual_integration_tests/` into `reference/ctk_official/` (gitignored, ~9 MB). Used as visual + code reference when implementing new widget descriptors so our preview matches the official library's look. `reference/ctk_official/README.md` has the file map.

**"Large Test Image" trick** — the official `image_example.py` "title-looking" gradient-with-text block is not a dynamic Label, it's a pre-rendered PNG (`test_images/large_test_image.png`) displayed via `CTkLabel(text="", image=CTkImage(...))`. If a user wants dynamic text on a gradient, pattern is `CTkLabel(text="My text", image=<gradient-only PNG>, compound="center")`.

---

## Semi-transparent images

PNG's alpha channel is preserved by PIL and respected by CTk's image rendering. Verified with `tools/test_transparent_png.py` using `Image.new("RGBA", ..., fill=(r, g, b, alpha))`. No workaround needed — same PNG with 50% alpha blends correctly over any parent colour.
