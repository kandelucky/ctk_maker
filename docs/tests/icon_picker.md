# Manual tests — Lucide Icon Picker (v0.0.26+)

რეგრესიის ხელით ტესტი. ქართული; technical terms (dialog, picker,
tint, hex...) ინგლისურად. ერთი project ყველა test-ზე — Quit + relaunch
საჭიროა მხოლოდ თუ სხვაგვარად მითითებულია.

> Run: `python main.py`. Standalone harness — `python tools/test_icon_picker.py`.

---

## Setup — Project + Assets tab

1. relaunch builder → New Project `IconTest` (default save) → Create
2. Assets tab → docked tree visible

---

## Test 1 — Entry points (3 გზა)

1. **`+ menu`** (Assets header) → `Lucide Icon...` (layout-list icon, Folder-ის ქვევით) → dialog 760×580 იხსნა
2. close → **right-click ცარიელ tree** → Add ▶ → `Lucide Icon...` → იგივე dialog
3. close → drop CTkButton on canvas → image_path → ⋯ → Image picker (480×480) header-ში `+ Lucide icon...` → click → Lucide picker

**Pass**: 3 entry points, dialog ყოველთვის ერთნაირი.

---

## Test 2 — Filter & select

dialog ღია, "All" active.

1. type `home` in search → ~5 icons → clear → ისევ ყველა
2. type `formatting` (tag search) → a-arrow icons
3. click `Accessibility (30)` → 30 icons → click `Arrows` → ისრები
4. click random cell → ლურჯი highlight + Apply enabled + preview pane updates (64×64 + name + tags)
5. click another → previous unhighlights, new highlighted

**Pass**: name+tag search, category switch, single-select with preview sync.

---

## Test 3 — Tint

icon selected.

1. clear Tint entry → type `#ff8800` → Enter → swatch ნარინჯისფერი → grid + preview retint
2. type `xyz` (invalid) → Enter → entry reverts to `#ff8800`
3. click swatch → ColorPickerDialog (taskbar-ის ზევით ჯდება) → pick green → OK → ყველა მწვანე

**Pass**: hex commit + invalid recovery + ColorPickerDialog integration.

---

## Test 4 — Size + Apply + smart routing

1. size dropdown: `64 px` → ცვლა `128 px` (preview pane არ იცვლება — output size-ია, არა preview)
2. icon `home` selected, tint orange → Apply → dialog closes → file at `assets/images/home.png` (128×128, ნარინჯისფერი)
3. + Folder → `icons` → right-click `icons/` → Add ▶ → Lucide Icon → pick + Apply → file at `assets/icons/<name>.png` (smart routing)
4. CTkButton → ⋯ Image picker → + Lucide icon → pick + Apply → Lucide closes, Image picker refreshes, new file auto-selected → OK → property assigned

**Pass**: size dropdown working, Apply writes correct size + tint, smart routing into right-clicked folder, nested Image picker flow.

---

## Test 5 — Cancel + double-click + sync

1. Cancel → dialog closes → no file created, no property change
2. ხელახლა გახსნა → double-click any cell → cell selects + Apply fires → dialog closes, file written
3. floating F10 + docked Assets ერთად ღია → Image picker-დან Lucide-ით pick → ორივე panel-ში file ჩანს (event_bus sync)

**Pass**: Cancel discards, double-click shortcut, dual-panel sync.

---

## Cleanup

- Quit + delete `~/Documents/CTkMaker/IconTest/`
