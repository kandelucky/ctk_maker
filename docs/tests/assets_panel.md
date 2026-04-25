# Manual tests — Assets panel (v0.0.25+)

რეგრესიის ხელით ტესტი. ქართული; technical terms (picker, drag-drop,
event_bus...) ინგლისურად. ერთი project ყველა test-ზე — Quit + relaunch
საჭიროა მხოლოდ Test 5-ის Save/Load-ისთვის.

> Run: `python main.py`.

---

## Setup — Project + Assets visible

1. relaunch builder → New Project `AssetsTest` → Create
2. Properties / Assets tab toggle — click Assets → docked tree visible

---

## Test 1 — Panel basics

1. Properties ↔ Assets tab toggle (no crash)
2. **F10** → floating Assets window გაიხსნა, contents იგივე
3. F10 ისევ → იხურება. floating + docked ერთად → ორივე ღია, sync-ში
4. Header: ერთ ხაზზე bold project name + dim front-truncated path
   (`...Documents\CTkMaker\AssetsTest`); separate "Project" title არ არის

**Pass**: docked + floating, compact header.

---

## Test 2 — + menu / Add ▶ submenu / right-click

1. **+ button** (Assets header) → menu order:
   `Folder → —— → Lucide Icon... / Image... / Font... → —— → Python File / Text File`
2. **right-click ცარიელი area** → menu: `New Folder / Add ▶ / —— / Open assets folder in Explorer`
3. **right-click folder row** → `Open in Explorer / Add ▶ / —— / New Subfolder / Rename / Delete`
4. **right-click file row** → `Open / Open in Explorer / Reimport / —— / Rename / Remove`
5. Add ▶ submenu identical 3 ადგილას: `Lucide Icon / Image / Font / —— / Python / Text`

**Pass**: every entry icon-ით (Lucide-ის ხატებით — folder-plus, image-plus, type, file-code, file-text, etc).

---

## Test 3 — Add image / font / folder + smart routing

1. + → Image → file picker → .png → file at `assets/images/X.png`, tree refresh
2. + → Font → .ttf → at `assets/fonts/Y.ttf` + tkextrafont registered
3. + → Folder → "icons" prompt → `assets/icons/` შეიქმნა
4. select `icons/` → + → Folder → "ui" → `assets/icons/ui/` (subfolder)
5. **smart routing**: right-click `icons/` → Add ▶ → Image → picker → file at `assets/icons/`, არა `images/`
6. + menu (no selection) → Image → file at `assets/images/` (legacy fallback)

**Pass**: ფაილები სწორ ფოლდერში, selected folder wins.

---

## Test 4 — Add Python / Text + starter content

1. + → Text File (.md) → "LICENSE" → `LICENSE.md` შეიქმნა, **არ იხსნება ავტომატურად**
2. + → Python File (.py) → "helpers" → `helpers.py` შეიქმნა, არ იხსნება
3. double-click `helpers.py` → IDLE / VSCode (edit verb) starter content-ით:
   v0.1 disclaimer + GitHub Issues + Buy me a Coffee links
4. double-click `LICENSE.md` → text editor starter `# LICENSE`-ით

**Pass**: no auto-open after creation, double-click → OS edit verb works.

---

## Test 5 — File operations

```
Setup: 1 .png + 1 .ttf imported, 1 custom folder `archive/`,
       canvas-ზე CTkButton image=that .png-ი დაყენებულია.
```

1. **Open in Explorer** (file row) → Explorer გაიხსნა, file მონიშნულია
2. **Reimport** → file picker → new content → file replaced in-place, references kept, widget visually განახლდა
3. **Rename file** → "renamed.png" → tree updated
4. **Rename folder** → "renamed_folder" → tree updated
5. **Remove file** → confirm → deleted, widget renders empty (no crash)
6. **Delete folder** (with read-only file inside) → "Delete '<name>' and N item(s)?" → Yes → recursive delete (`_force_remove_readonly` handles read-only attrs)
7. **Save/Load roundtrip**: Save (Ctrl+S) → Quit → reopen → tree state persists

**Pass**: all ops work, references survive, read-only attrs handled.

---

## Test 6 — Tree visualization + info panel

```
Setup: 1 .png 200×100, 1 .ttf "Comic Sans MS", 1 .md, 1 .py, 1 folder.
```

1. row icons by kind: folder / image / type / file-text / file-code / file (2-space gap before name)
2. recursive nesting: parent folder count includes children
3. **info panel** on selection:
   - .png → filename + Size KB + Dimensions WxH + 140×140 thumbnail
   - .ttf → filename + Size + Family + Format
   - folder → name + size
   - clear selection → info panel იცარიელდება

**Pass**: kind-specific icons + info, image preview thumbnail.

---

## Test 7 — Multi-select + drag-and-drop

```
Setup: 3 .png in `images/` + custom `archive/` folder.
```

1. **multi-select**: click → Ctrl+click → Ctrl+click (3 selected, ttk extended mode)
2. drag → ghost Toplevel "3 items" (semi-transparent) cursor-ის გვერდით
3. `archive/` highlights `#26486b` როცა cursor მასზეა → drop → all 3 move
4. **single drag**: 1 file → drop on `archive/` → ghost "1 item"
5. **empty area drop** = root: drag from `archive/` to ცარიელ space → file → `assets/`
6. **invalid drop refused**: drag `parent` folder onto `parent/child` → no highlight, no move
7. **conflict on drop**: drag `a.png` to folder that already has `a.png` → warning "already exists, skipping"

**Pass**: drag/drop with ghost + target highlight; invalid drops + conflicts handled.

---

## Test 8 — Sync between docked + floating

1. F10 → floating + docked ღია ერთად
2. floating window → + → Image → file added
3. docked tree should reflect the new file immediately (event_bus `dirty_changed`)
4. ანალოგიურად: docked → + → Folder → floating refreshes

**Pass**: event_bus keeps both panels in sync.

---

## Cleanup

- Quit + delete `~/Documents/CTkMaker/AssetsTest/`
