# Manual tests — Assets panel (v0.0.23 / v0.0.24)

რეგრესიის ხელით ტესტი. სცენარები ქართულად; technical terms (CTkLabel,
picker, drag-drop...) ინგლისურად. ყოველი test ცარიელი სუფთა session-ით
იწყება (Quit + relaunch) თუ არ არის სხვაგვარად მითითებული.

> Run: `python main.py` ფიქსურ ტერმინალში.

---

## Setup A — Assets panel-ის გამოჩენა

1. გახსენი builder → Quit-ით ჩაკეტე ნებისმიერი ღია სესია → relaunch
2. New Project → Name: `AssetsTest` → Save to: default → Create
3. Properties panel-ის ზედა ბარში ორი tab — **Properties** + **Assets**
4. Save (Ctrl+S)

---

## Test 1 — Docked tab toggle

**Setup**: Setup A.

1. Properties tab აქტიურია (default)
2. click Assets tab → panel იცვლება → ხილვადია project name + path + tree
3. click Properties tab → ისევ Properties (widget rows)

**Pass**: ორი tab toggle მუშაობს, არ ხდება crash.

---

## Test 2 — Floating window (F10)

**Setup**: Setup A.

1. F10 → ცალკე ფანჯარა "Assets" გაიხსნა (ProjectWindow)
2. ფანჯარის contents იგივეა, რაც docked tab-ი
3. F10 ისევ → ფანჯარა იხურება
4. Both windows simultaneously: F10 (floating) + click Assets tab (docked)
   → ორივე გახსნილია, ორივე იგივე state-ში

**Pass**: დოკ + floating both work, in sync.

---

## Test 3 — Compact header

**Setup**: Setup A.

1. Header-ში ერთ ხაზზე: bold project name (`AssetsTest`) + dim path
2. Path is front-truncated (e.g. `...Documents\CTkMaker\AssetsTest`) —
   width-კი არ აშლის dialog-ის ზომას
3. ცალკე "Project" title არ არის
4. ცალკე "Reveal in Explorer" ღილაკი არ არის (იხსნება მხოლოდ
   right-click context menu-დან)

**Pass**: header კომპაქტურია, ერთი row-ი.

---

## Test 4 — + menu

**Setup**: Setup A.

1. Header-ის მარჯვნივ "+" ღილაკი
2. Click → dropdown menu:
   - Image...
   - Font...
   - ── (separator)
   - Folder
   - Text File (.md)
   - Python File (.py)

**Pass**: 5 punkt + 1 separator.

---

## Test 5 — + Image / + Font

**Setup**: Setup A.

1. + → Image... → file picker → .png file → 
   → file copied to `assets/images/X.png` → 
   → tree refreshes, ფაილი ჩანს
2. + → Font... → file picker → .ttf → 
   → file copied to `assets/fonts/Y.ttf` → 
   → ფონტი registered with tkextrafont

**Pass**: ფაილები assets/-ში, tree updated.

---

## Test 6 — + New Folder

**Setup**: Setup A.

1. select `images/` folder
2. + → Folder → prompt "Folder name:" → type "icons" → OK
3. tree refreshes → `assets/images/icons/` folder ჩანს

ნაბიჯი 1-ის გარეშე (selection clear):
4. + → Folder → "icons2" → OK
5. `assets/icons2/` ფოლდერი (root-ში) ჩანს

**Pass**: ფოლდერი იქმნება selected location-ში ან root-ში.

---

## Test 7 — + New Text File (.md)

**Setup**: Setup A.

1. + → Text File (.md) → prompt "Filename:" → type "LICENSE" → OK
2. tree → `LICENSE.md` ფაილი ჩანს
3. ავტომატურად გაიხსნა OS default editor-ში starter content-ით:
   `# LICENSE\n\n`

**Pass**: ფაილი იქმნება + ავტო-open editor-ში.

---

## Test 8 — + New Python File (.py)

**Setup**: Setup A.

1. + → Python File (.py) → prompt → "helpers" → OK
2. tree → `helpers.py` ფაილი ჩანს
3. ავტომატურად IDLE / VSCode-ში გაიხსნა starter docstring-ით:
   `"""helpers.py — module description here."""`

**Pass**: .py ფაილი + automatic-ად editor-ში.

---

## Test 9 — Right-click empty area

**Setup**: Setup A.

1. Right-click ცარიელი ფართობი (tree-ის ბოლოში)
2. Context menu:
   - Import Image...
   - Import Font...
   - ── 
   - New Folder...
   - New Text File...
   - New Python File...

**Pass**: 5 punkt + 1 separator.

---

## Test 10 — Right-click on folder

**Setup**: Setup A. ერთი ფოლდერი (e.g. `images/`).

1. Right-click `images/` row
2. Context menu:
   - Reveal in Explorer
   - ── 
   - Import Image here...
   - Import Font here...
   - ── 
   - New Subfolder...
   - New Text File...
   - New Python File...
   - ── 
   - Rename...
   - Delete folder...

**Pass**: 8 punkts (with separators).

---

## Test 11 — Right-click on file

**Setup**: Setup A. ერთი .png + ერთი .ttf imported.

1. Right-click .png row
2. Context menu:
   - Open
   - Reveal in Explorer
   - Reimport...
   - ── 
   - Rename...
   - Remove from project...

**Pass**: 5 punkts.

---

## Test 12 — Reveal in Explorer

**Setup**: Setup A. ერთი .png ფაილი.

1. Right-click .png → Reveal in Explorer
2. Windows Explorer გაიხსნა, file მონიშნულია (`/select,` flag)

**Pass**: Explorer იხსნება და file highlighted.

---

## Test 13 — Reimport

**Setup**: Setup A. icon.png imported. ცალკე desktop-ზე new-icon.png
(სხვა content, იგივე საქმე).

1. Right-click icon.png → Reimport... → file picker → desktop/new-icon.png → OK
2. icon.png-ის შინაარსი ცვლილდება new-icon-ის ცონტენტით (path არ შეიცვლება)
3. ყველა ვიჯეტი რომელიც icon.png-ს იყენებდა, ავტომატურად განახლდება

**Pass**: file replaced in-place, references kept.

---

## Test 14 — Remove file

**Setup**: Setup A. ერთი .png imported, რომელიმე ვიჯეტს მიცემული.

1. Right-click .png → Remove from project...
2. Confirmation dialog: "Remove 'X.png'? This deletes... cannot be undone..."
3. Yes → file deleted from disk
4. ვიჯეტის image=path → render-ში graceful (no image, no crash)

**Pass**: File deleted, widget renders without image.

---

## Test 15 — Rename file

**Setup**: Setup A. ერთი .png ფაილი.

1. Right-click .png → Rename → simpledialog
2. Type "renamed.png" → OK
3. tree refresh → ფაილი ცვლი სახელს

**Pass**: file renamed on disk.

---

## Test 16 — Rename folder

**Setup**: Setup A. ფოლდერი `myfolder` (შექმნილი + Folder-ით).

1. Right-click folder → Rename → "renamed"
2. tree refresh → folder ცვლი სახელს

**Pass**: folder renamed.

---

## Test 17 — Delete folder (recursive count + warning)

**Setup**: Setup A. folder `assets/test_dir/` 5 file-ით + 1 subfolder + 2 file ში.

1. Right-click `test_dir/` → Delete folder...
2. Confirmation: "Delete 'test_dir' and 8 item(s) inside it?\n\nPath: ...\n\nThis deletes the folder from disk..."
3. Yes → ფოლდერი + ყველაფერი მის შიგნით წაიშლა (`shutil.rmtree`)

**Pass**: count გვიჩვენებს ცადომდე, რეცურსიული წაშლა.

---

## Test 18 — Double-click file → OS open

**Setup**: Setup A.

1. Double-click .png row → Windows Photos ან image viewer გახსნა
2. Double-click .ttf row → Windows Font Viewer გახსნა
3. Double-click .md row → text editor (default association)
4. Double-click .py row → IDLE ან VSCode

**Pass**: each kind → its OS default app.

---

## Test 19 — Recursive tree (custom folders)

**Setup**: Setup A.

1. + Folder → "icons" → enter
2. select `icons` → + Folder → "ui" → enter
3. select `icons/ui` → + Image → some.png → enter
4. tree-ში ხეხელად ჩანს:
   ```
   📁 fonts/  (0)
   📁 icons/  (1)
     📁 ui/  (1)
        🖼 some.png
   📁 images/  (0)
   📁 sounds/  (0)
   ```

**Pass**: recursive levels work, custom folders alongside default skeleton.

---

## Test 20 — Per-row icons (Lucide kinds)

**Setup**: Setup A. ერთი .png + ერთი .ttf + ერთი .md + ერთი .py + ერთი folder.

1. Tree row-ებში icon კი გამოვა kind-ის მიხედვით:
   - folder → folder ხატი
   - .png → image (პატარა სურათი)
   - .ttf → type (Aa)
   - .md → file-text
   - .py → file-code
2. სიცარიელე text-სა და icon-ს შორის — 2 leading space

**Pass**: ცხადი ვიზუალური განცხდება.

---

## Test 21 — Info panel (selection metadata)

**Setup**: Setup A. ერთი .png 200×100 + ერთი .ttf "Comic Sans MS".

1. select .png → info panel:
   - filename
   - Size: XX KB
   - Dimensions: 200 × 100 px
   - thumbnail preview (140×140 max)
2. select .ttf → info panel:
   - filename
   - Size
   - Family: Comic Sans MS
   - Format: TTF
3. select folder → info panel: name + size of folder (or empty)
4. clear selection → info panel იცარიელდება

**Pass**: each kind → kind-specific metadata + thumbnail for images.

---

## Test 22 — Multi-select (Ctrl+click)

**Setup**: Setup A. 3 ფაილი + 2 ფოლდერი.

1. click first file → selected
2. Ctrl+click second file → both selected (highlighted)
3. Ctrl+click third file → 3 selected
4. Shift+click first file → 1-3 range selected (depending on order)

**Pass**: native ttk.Treeview multi-select works.

---

## Test 23 — Drag move single file

**Setup**: Setup A. `images/` folder + custom `icons/` folder + ერთი .png in `images/`.

1. press + drag .png from `images/` to `icons/` 
2. drag ghost: "1 item" Toplevel cursor-ის გვერდით (semi-transparent)
3. `icons/` row highlights blue (`#26486b`) როცა cursor მასზეა
4. release on `icons/` → file moves there
5. tree refresh — file ჩანს `icons/`-ში, არა `images/`-ში

**Pass**: drag-drop move, ghost ხილვადი, target highlight.

---

## Test 24 — Drag move multiple files

**Setup**: Setup A. 3 .png in `images/` + custom `archive/` folder.

1. select first file → Ctrl+click second → Ctrl+click third (3 selected)
2. drag → ghost shows "3 items"
3. drop on `archive/` → all 3 move there

**Pass**: multi-select drag.

---

## Test 25 — Drop on empty area = root

**Setup**: Setup A. subfolder `images/icons/` with one .png inside.

1. drag .png from `images/icons/` → drop on tree-ის ცარიელ space (ბოლოში)
2. file moves to `assets/` root

**Pass**: empty-area drop = root drop.

---

## Test 26 — Invalid drag refused

**Setup**: Setup A. folder `parent` containing folder `child`.

1. drag `parent` folder → try to drop on `child`
2. drop target highlight არ შემოვა (legal check)
3. release → არაფერი მოხდა (no shutil.move)

**Pass**: descendant-drop refused.

---

## Test 27 — Conflict on drop

**Setup**: Setup A. file `a.png` in `images/` + same name `a.png` in `icons/`.

1. drag `a.png` from `images/` → drop on `icons/`
2. warning: "'a.png' already exists in 'icons'. Skipping."
3. file stays in `images/`

**Pass**: conflict detected, warning shown.

---

## Test 28 — Smart routing on right-click import

**Setup**: Setup A. custom `icons/` folder.

1. Right-click `icons/` → Import Image here... → pick .png
2. file copied to `assets/icons/`, არა `assets/images/`

ანალოგიურად + menu without selection:

3. + → Image (no selection) → pick .png
4. file copied to `assets/images/` (legacy auto-route)

**Pass**: context-aware routing.

---

## Final cleanup

- Quit project
- Delete `~/Documents/CTkMaker/AssetsTest/` test data
