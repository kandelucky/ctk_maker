# Bugs — გასასწორებელი ბაგები

> რეალური bug-ები, რომელიც გვიშლის ხელს ან მოსალოდნელ behavior-ს არღვევს. პრიორიტეტი გასწორებაზე.

---

## 🐛 Orientation editor — CTkSlider orientation change broken

Changing `orientation` property on CTkSlider doesn't update widget visually / recreate. `recreate_triggers = {"orientation"}` is set but the flip doesn't take effect. CTkProgressBar orientation works (has same `recreate_triggers`).

**Investigation**: check `on_prop_recreate` hook for CTkSlider vs CTkProgressBar difference. CTkSlider likely missing the width/height swap logic that CTkProgressBar has.

---

## 🐛 Drag-scrub Escape cancel — not implemented

Pressing Escape during drag-scrub should revert to original value. Currently Escape does nothing; release commits the current value.

**Fix**: in `drag_scrub.py` `_on_motion` or add `<Escape>` binding → reset `_active_value` to `_start_value` + destroy editor without commit.

---

## 🐛 Rapid undo/redo grid reparent — button loss

**Symptom**: spam-pressing Ctrl+Z / Ctrl+Y on a grid-reparent sequence can cause a button to "disappear from memory" — only 4 of 5 come back on redo.

**Not reproducible** on single steps. Likely a race in destroy / recreate path when `widget_reparented` fires mid-replay while history is still suspended.

**Investigation**: add instrumentation in `widget_lifecycle.on_widget_reparented` + history replay. Look for events firing during `history.suspend()` context.
