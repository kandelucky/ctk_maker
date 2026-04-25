# Manual tests — Lucide Icon Picker (v0.0.25+)

რეგრესიის ხელით ტესტი. სცენარები ქართულად; technical terms (dialog,
picker, tint, hex...) ინგლისურად. ყოველი test ცარიელი სუფთა session-ით
იწყება (Quit + relaunch) თუ არ არის სხვაგვარად მითითებული.

> Run: `python main.py`. Standalone harness — `python tools/test_icon_picker.py`.

---

## Setup A — Project + ხილვადი Assets panel

1. Quit ნებისმიერი ღია session → relaunch
2. New Project → Name: `IconTest` → Save to: default → Create
3. click Assets tab (docked) → tree visible
4. Save (Ctrl+S)

---

## Test 1 — Dialog ხსნა Project window-ის + menu-დან

**Setup**: Setup A.

1. click `+` button → menu: Folder / —— / **Lucide Icon...** / Image... / Font... / —— / ...
2. layout-list iconi ჩანს Lucide Icon entry-ის გვერდით
3. click Lucide Icon → dialog 760×580 იხსნება
4. Layout: Search bar (top) → Sidebar (left, 42 categories + "All") → Grid (center, 6 cols) → Preview (right, 64×64)
5. Footer: Cancel + Apply (Apply disabled)

**Pass**: dialog ხსნა, layout სრული.

---

## Test 2 — Dialog ხსნა right-click Add ▶ submenu-დან

**Setup**: Setup A.

1. right-click ცარიელ tree area-ზე → Add ▶ → **Lucide Icon...** (top entry)
2. dialog იხსნება იგივე layout-ით

**Pass**: submenu integration.

---

## Test 3 — Dialog ხსნა Image picker-დან (Properties panel)

**Setup**: Setup A. canvas-ზე drop CTkButton → image_path property → ⋯ click.

1. Image picker dialog იხსნება (480×480) → header-ში ორი ღილაკი: `+ Import image...` და `+ Lucide icon...`
2. click `+ Lucide icon...` → Lucide picker იხსნება

**Pass**: nested dialog, ორივე ღილაკი ჩანს.

---

## Test 4 — Category filter

**Setup**: dialog ღია (any way).

1. default: "All" highlighted (ლურჯი) → grid shows ~400 icons + count "showing 400 of 1699 — refine search"
2. click "Accessibility (30)" → grid → 30 icons → count "30 icons"
3. click "Arrows" → ისარების icons → count updates

**Pass**: category click → grid refresh + count.

---

## Test 5 — Search by name

**Setup**: dialog ღია, "All" active.

1. type `home` in Search → grid filter → ~5 icons (home, home-plus...)
2. clear search → ისევ ყველა icon
3. type `xyz123` → grid empty → "No icons match."

**Pass**: name substring search.

---

## Test 6 — Search by tag

**Setup**: dialog ღია, "All" active.

1. type `formatting` → icons with "formatting" tag (a-arrow-down, a-arrow-up...)
2. type `magic` → sparkles, wand icons

**Pass**: tag search.

---

## Test 7 — Click select + Apply enable

**Setup**: dialog ღია.

1. click random icon cell → cell ლურჯად (#094771) → Apply enabled
2. Preview pane: 64×64 icon + name + tags
3. click another → previous unhighlights, new highlighted, preview updates

**Pass**: single-select, preview sync.

---

## Test 8 — Tint via hex entry

**Setup**: dialog ღია, icon selected.

1. clear Tint entry → type `#ff8800` → Enter → swatch ნარინჯისფერი → grid + preview retint
2. Type invalid `xyz` → Enter → entry reverts to last valid

**Pass**: tint commit + invalid-input recovery.

---

## Test 9 — Tint via color picker

**Setup**: dialog ღია, icon selected.

1. click swatch (24×24 colored box) → ColorPickerDialog იხსნება
2. pick green → OK → swatch + entry + grid + preview ყველა მწვანე

**Pass**: ColorPickerDialog integration.

---

## Test 10 — Apply writes to target dir (Project window)

**Setup**: Setup A, dialog opened from + menu.

1. select `home` icon → tint `#ff8800` → Apply
2. dialog closes
3. Assets tree: `images/home.png` row appeared (orange tint visible if you preview)

**Pass**: tinted PNG saved + tree refreshes.

---

## Test 11 — Apply writes to right-clicked folder

**Setup**: Setup A. Create `assets/icons/` folder via + → Folder.

1. right-click `icons/` row → Add ▶ → Lucide Icon → pick + Apply
2. file lands at `assets/icons/<name>.png` (NOT `images/`)

**Pass**: smart routing into right-clicked folder.

---

## Test 12 — Apply from Image picker writes to images + auto-select

**Setup**: Setup A. canvas-ზე CTkButton + image picker → Lucide picker.

1. pick `star` → Apply
2. Lucide picker closes → Image picker still open → tree refreshed → `star.png` selected (ლურჯი row)
3. OK → property assigned → docked Assets panel-ში `images/star.png` ჩანს (sync via event_bus)

**Pass**: nested-dialog flow + sync.

---

## Test 13 — Cancel returns nothing

**Setup**: dialog ღია, icon selected, tint changed.

1. Cancel → dialog closes
2. no file created in target dir
3. property unchanged (if from Image widget flow)

**Pass**: Cancel discards.

---

## Test 14 — Double-click = Apply

**Setup**: dialog ღია.

1. double-click any cell → cell selects + Apply fires immediately
2. dialog closes, file written

**Pass**: double-click shortcut.

---

## Test 15 — Standalone harness

**Setup**: Quit builder. Run `python tools/test_icon_picker.py`.

1. small window: "Open Lucide Icon Picker" button + output folder label
2. click → dialog opens → pick + Apply
3. window shows 96×96 preview + path label
4. file in `tools/test_output/<name>.png`

**Pass**: harness works in isolation.

---

## Final cleanup

- Quit
- Delete `~/Documents/CTkMaker/IconTest/` + `tools/test_output/` test data
