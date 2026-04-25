# Manual tests — Font system (v0.0.22)

რეგრესიის ხელით ტესტი. ჯერ აუტო-ტესტები არაა — გამოქვეყნებამდე დაემატება.
სცენარები ქართულად, technical terms (CTkLabel, picker, cascade...) ინგლისურად.

> Run: `python main.py` ფიქსურ ტერმინალში; თითოეული ტესტი ცარიელი
> სუფთა session-ით იწყება (Quit + relaunch) თუ არ არის სხვაგვარად
> მითითებული.

---

## Setup A — სუფთა პროექტი

1. გახსენი builder → Quit-ით ჩაკეტე ნებისმიერი ღია სესია → relaunch
2. New Project → Name: `FontTest` → Save to: default → Create
3. Place ერთ canvas-ზე ერთი თითო:
   - 3x CTkButton, 2x CTkLabel
   - 1x CTkEntry, 1x CTkTextbox
   - 1x CTkCheckBox, 1x CTkRadioButton, 1x CTkSwitch
   - 1x CTkComboBox, 1x CTkOptionMenu, 1x CTkSegmentedButton
   - 1x CTkScrollableFrame (label_text="Header"), 1x CTkTabview
4. Save (Ctrl+S)

---

## Test 1 — Per-widget font import (.ttf ფაილიდან)

**Setup**: Setup A.

1. select Button 1 → Properties → Text section → "Font" row → ⋯ ღილაკი
   → FontPickerDialog იხსნება, palette ცარიელია (empty state hint)
2. + Import file... → ფაილ-პიკერი → აირჩიე ნებისმიერი .ttf (e.g. Kenney Future)
   → palette-ში გამოჩნდება family + preview "AaBb 123"
   → row auto-selected
3. OK → Button 1-ის ტექსტი ცვლის ფონტს იმპორტირებულზე

**Pass**: Button 1 visually changes; მე-2 და მე-3 Button უცვლელია.

---

## Test 2 — System font via secondary picker (auto-copy)

**Setup**: Setup A.

1. Button 1 → font picker → + Add system font...
   → SystemFontPickerDialog (full OS list, search box)
2. search "Comic" → Comic Sans MS → Add (or double-click)
   → main picker reopens-ს, palette-ში Comic Sans MS გამოჩნდება, auto-selected
3. OK → Button 1 — Comic Sans MS
4. Project window (F10) → assets/fonts/ tree → უნდა იყოს `comic.ttf`
   (Windows-ზე — registry lookup → copy to project)

**Pass**: ფონტი ვიზუალურად Comic Sans-ი + ფაილი ფიზიკურად ფოლდერშია.

---

## Test 3 — Cascade: scope=All [Type], no overrides

**Setup**: Setup A. სამივე Button default ფონტით.

1. Button 1 → font picker → Comic Sans MS → "Apply to: All Buttons" → OK
   → არ უნდა გამოჩნდეს რაიმე dialog (no overrides exist)
2. სამივე Button — Comic Sans MS ფონტი

**Pass**: სამივე ღილაკი ერთდროულად შეიცვალა.

---

## Test 4 — Cascade: per-widget override survives type default

**Setup**: Setup A.

1. Button 2 → font picker → Impact → "Apply to: This widget" → OK
   → Button 2 — Impact (per-widget override)
2. Button 1 → font picker → Comic Sans MS → "All Buttons" → OK
   → ChoiceDialog: "1 widget(s) carry a per-widget font override"
   → click "Only default"
3. Button 1, Button 3 — Comic Sans MS
4. Button 2 — ისევ Impact (override გადარჩა)

**Pass**: override-ი სიცოცხლეშია, default-მა მხოლოდ override-ის გარეშე ღილაკები შეცვალა.

---

## Test 5 — Cascade: "All widgets" — clear overrides

**Setup**: Test 4-ის ბოლო state.

1. Button 1 → font picker → Times New Roman → "All Buttons" → OK
   → ChoiceDialog: "1 widget(s) carry a per-widget font override"
   → click "All widgets"
2. სამივე Button — Times New Roman (Button 2-ის override გადასახადი)

**Pass**: Override გადასუფთავდა, ყველა Button ერთ ფონტზეა.

---

## Test 6 — Cascade: All in project + type defaults conflict

**Setup**: Setup A.

1. Button 1 → font picker → Comic Sans MS → "All Buttons" → OK
2. Label 1 → font picker → Impact → "All in project" → OK
   → ChoiceDialog: "1 widget type(s) carry their own default (CTkButton)"
   → click "Only default"
3. Buttons — ისევ Comic Sans (per-type default ცოცხალია)
4. Labels, Entry, etc. — Impact

ნაბიჯი 2 ხელახლა, ოღონდ "All widgets" → ყველა — Impact (per-type CTkButton default წაიშალა).

**Pass**: dialog ჩანს, "Only default" იცავს per-type-ს, "All widgets" ცილობს.

---

## Test 7 — Use default — clear cascade entry

**Setup**: Setup A. project-wide default ჩაყენებული Comic Sans-ზე.

1. ნებისმიერ ვიჯეტზე → font picker → "Use default" → "All in project" → OK
   → arno dialog (clearing default never breaks intent)
   → font_defaults["_all"] წაიშალა
2. ვიჯეტები ბრუნდებიან Tk default-ზე

**Pass**: cascade key cleared without confirmation, ყველა Tk default-ში.

---

## Test 8 — Save/Load roundtrip

**Setup**: Setup A. რამდენიმე ვიჯეტს ცალკე ფონტი + cascade default.

1. Save → Quit → relaunch → File → Open → FontTest project
2. Editor → ფონტები ისეთივეა, როგორც Save-მდე
3. Preview ▶ → preview-შიც იგივე ფონტები

**Pass**: Editor + preview ორივე font-ი იცვლება Save-მდე.

---

## Test 9 — ScrollableFrame label font

**Setup**: Setup A.

1. ScrollableFrame → Properties → Label Text = "Header"
2. Label Font row → ⋯ → Comic Sans MS → "This widget" → OK
3. Header-ის ფონტი იცვლება Comic Sans-ზე

**Pass**: title ფონტი იცვლება (frame body — სხვა ფონტი თუ default).

---

## Test 10 — ComboBox / OptionMenu popup item font

**Setup**: Setup A.

1. ComboBox → font picker → Comic Sans MS → "This widget" → OK
   → field-ში ფონტი იცვლება
2. ComboBox-ზე click → dropdown ▼ → popup-ის row-ები (Option 1, 2, 3) — Comic Sans MS

**Pass**: ფონტი parent + popup-შიც.

---

## Test 11 — CTkTabview tab buttons font

**Setup**: Setup A.

1. Tabview → Properties → Text section → Tab Font → ⋯ → Comic Sans MS → OK
2. Tab 1 / Tab 2 / Tab 3 button-ების ფონტი იცვლება

**Pass**: tab labels — Comic Sans MS.

---

## Test 12 — CTkLabel italic clip workaround

**Setup**: Setup A.

1. Label 1 → font picker → ნებისმიერი italic / script font (e.g. Brush Script,
   Comic Sans Italic) → OK
2. ბოლო character (e.g. "l") არ უნდა იყოს clipped

**Pass**: ბოლო ასო ფიზიკურად ჩანს.

---

## Test 13 — Dropdown popup hides on app deactivate

**Setup**: Setup A.

1. ComboBox → click ▼ → popup ხილულია
2. Alt+Tab → სხვა app-ზე
3. ComboBox-ის popup უნდა გაქრეს (ან ჩავიდეს უკან, არა topmost)

**Pass**: სხვა აპის ფანჯარა popup-ს ფარავს.

---

## Test 14 — Re-import same font (already-loaded path)

**Setup**: Setup A. ერთხელ უკვე იმპორტირებული Kenney Future.ttf.

1. ისევ font picker → + Import file... → ისევ Kenney Future.ttf
2. არ უნდა გამოჩნდეს "Font registered with no family" warning
3. picker-ში family ისევ ჩანს, არჩევა მუშაობს

**Pass**: silent dedup, warning არ იყო.

---

## Test 15 — Stem fallback for fonts without family metadata

**Setup**: Setup A. .ttf ფაილი რომლის PIL family extraction failed-ი.

1. import font that's known to have unusual / missing name table
2. picker-ში გამოჩნდება family-ად ფაილის stem (e.g. `MyFont.ttf` → "MyFont")
3. არ არის "no family" warning

**Pass**: ფონტი palette-ში, stem-ად სახელი.

---

## Test 16 — Preview includes bundled fonts (exporter integration)

**Setup**: Setup A. Button-ს custom .ttf ფონტი (assets/fonts/-ში copied).

1. Save → Preview ▶
2. preview window გაიხსნება
3. Button-ის ფონტი — იგივე custom font (არა Tk default)

**Pass**: tkextrafont რეგისტრაცია generated kod-ში მუშაობს.

---

## Test 17 — File-system scan picks up dropped fonts

**Setup**: Setup A. project-ის assets/fonts/ ფოლდერში ხელით ჩავაგდე .ttf
(Explorer-დან drag-and-drop).

1. გადადი builder-ში → ნებისმიერი widget → font picker
2. picker palette-ში გამოჩნდება ახალი ფონტი (lazy filesystem scan)

**Pass**: external file copy reflected, no relaunch needed.

---

## Test 18 — Override-only kwargs land in export (regression)

**Setup**: Setup A.

1. CTkSegmentedButton → set width=400 in editor
2. Save → Preview
3. preview-ში SegmentedButton-ის width — 400px (no auto-shrink)

**Pass**: dynamic_resizing=False ემიტდა, width რჩება როგორც დაყენებული.

---

## Final cleanup

- Quit project
- Delete `~/Documents/CTkMaker/FontTest/` თუ test data არ გჭირდება
