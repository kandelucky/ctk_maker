# Manual tests — Font system (v0.0.24+)

რეგრესიის ხელით ტესტი. ქართული; technical terms (cascade, picker,
tkextrafont, label_font...) ინგლისურად. ერთი project ყველა test-ზე —
Quit + relaunch მხოლოდ Test 5-ის Save/Load ნაწილისთვის.

> Run: `python main.py`.

---

## Setup — FontTest project + canvas widgets

1. relaunch → New Project `FontTest` → Create
2. canvas-ზე drop:
   - 3x CTkButton, 2x CTkLabel
   - 1x CTkEntry, 1x CTkTextbox, 1x CTkCheckBox, 1x CTkRadioButton, 1x CTkSwitch
   - 1x CTkComboBox, 1x CTkOptionMenu, 1x CTkSegmentedButton
   - 1x CTkScrollableFrame (label_text="Header"), 1x CTkTabview

---

## Test 1 — Font sources

1. select Button 1 → Properties → Font row → ⋯ → FontPickerDialog (palette empty initially)
2. **+ Import file...** → .ttf → palette-ში family + preview "AaBb 123", auto-selected → OK → Button 1 — new font
3. **+ Add system font...** → SystemFontPickerDialog → search "Comic" → Comic Sans MS → Add → main picker reopens, palette-ში Comic Sans → OK
4. assets/fonts/-ში **`comic.ttf`** copy (Windows registry lookup)
5. **re-import same .ttf** → silent dedup, no "no family" warning
6. .ttf without family metadata → palette-ში stem-ად სახელი (e.g. `MyFont.ttf` → "MyFont")

**Pass**: 4 font sources work; auto-copy from registry; dedup silent.

---

## Test 2 — Picker UX

1. layout top→bottom: header (Import / Add system / help) → preview pane → palette list → "Apply to:" segmented → Reset / Cancel / Apply
2. **preview pane**: text input + 13px + 24px sample labels at fixed height 110 (dialog არ იცვლის ზომას ფონტის ცვლისას)
3. type custom text in preview entry → both labels update live; click palette rows → preview reflects family
4. **right-click row → Remove from project** → confirm → imported font deleted from disk; system_fonts entry removed; cascade defaults pointing at it cleared
5. **footer hierarchy** (grid + spacer): Reset (70px tertiary, left) | Cancel (90px) + Apply (140px primary, right)
6. **segmented scope** control: 3 segments — `Just this widget` / `All Buttons` / `Whole project`

**Pass**: layout stable, live preview, remove cleans references, button hierarchy clear.

---

## Test 3 — Per-widget application + Reset

1. Button 2 → font picker → Impact → "Just this widget" → Apply → only Button 2 changes
2. Button 1 ი Button 3 უცვლელი
3. Button 2 → font picker → click selected row again? → click **Reset** → Button 2 ბრუნდება Tk default-ზე (cascade entry cleared)

**Pass**: per-widget override; Reset clears scope-level entry.

---

## Test 4 — Cascade scope literalism (v0.0.24)

```
Setup: 3 Buttons; Button 2 has Impact override (per Test 3).
```

1. Button 1 → font picker → Comic Sans MS → "All Buttons" → Apply
   → info dialog: "1 widget(s) currently use a custom font. Their override will be cleared." → OK
2. სამივე Button → Comic Sans (Button 2-ის Impact წაშლილი)
3. ცალკე — Label → font picker → Verdana → "Whole project" → Apply
   → no dialog (no overrides to warn about)
4. ყველა ვიჯეტი (Buttons + Labels + Entry + ...) → Verdana
5. ხელახლა "Whole project" → Times New Roman → ყველა → Times (per-type CTkButton entry → Comic ასევე წაშლილი — scope literal)

**Pass**: scope literal interpretation, info dialog only when overrides exist.

---

## Test 5 — Save/Load + Preview (exporter)

1. რამდენიმე ვიჯეტს custom .ttf font + cascade default → Save (Ctrl+S)
2. Quit → relaunch → File → Open → FontTest → editor + custom fonts persist
3. **Preview ▶** → spawned subprocess → Preview window-ში იგივე ფონტები (tkextrafont registration helper-ი generated code-ში)
4. **filesystem drop**: ხელით drop .ttf into `assets/fonts/` → next picker open shows it (lazy scan)

**Pass**: font_defaults + per-widget font_family persist; preview matches editor; FS scan picks up dropped files.

---

## Test 6 — Special widget kinds

1. **ScrollableFrame label_text font**: Label Text="Header" → Label Font row → ⋯ → Comic Sans → Apply → Header changes (frame body unaffected)
2. **ComboBox / OptionMenu popup**: ComboBox → font picker → Comic Sans → click ▼ → popup rows (Option 1, 2, 3) ფონტი — Comic Sans
3. **Tabview tab buttons**: Tabview → Tab Font → Comic Sans → Tab 1 / Tab 2 / Tab 3 button labels font changes
4. **CTkLabel italic clip**: Label → italic / script font (Brush Script, Comic Sans Italic) → ბოლო ასო visible (padx=4 absorbs slant overhang)

**Pass**: font_kwarg + post-construction configure paths all work.

---

## Test 7 — Side bugs (regression)

1. **dropdown popup hides on app deactivate**: ComboBox → ▼ → popup ხილული → Alt+Tab → popup უნდა გაქრეს (ან non-topmost)
2. **SegmentedButton width persists in export**: SegmentedButton → set width=400 → Save → Preview → preview-ში width=400 (no auto-shrink, dynamic_resizing=False emitted)

**Pass**: regressions clean.

---

## Cleanup

- Quit + delete `~/Documents/CTkMaker/FontTest/`
