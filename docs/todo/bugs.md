# Bugs — გასასწორებელი ბაგები

> რეალური bug-ები, რომელიც გვიშლის ხელს ან მოსალოდნელ behavior-ს არღვევს. პრიორიტეტი გასწორებაზე.

---

## 🐛 Nested-widget drag — selection vs. widget visual mismatch on high-DPI

**Symptom:** Dragging a widget inside a Frame on a 125 % DPI screen, the selection outline tracks the cursor but the actual widget visual drifts. The further the widget sits from the Frame's origin (bottom-right corner = worst case), the bigger the offset. After release the widget stays at the drifted visual position on canvas, while the model (`node.properties["x"/"y"]`) + Preview (`Ctrl+R`) show the widget at the cursor position. So preview != canvas visual for the same project state.

**Screenshot:** selection rectangle floats in the middle of the Frame while the dragged Button sits in the lower-right corner.

**Root cause hypothesis (unverified):** Three places in the drag / property flow use different zoom factors:
- `drag.py` motion → `place_configure(x = new_x * canvas_scale)` where `canvas_scale = user_zoom × DPI`
- `_handle_coord_prop` (release) → `place_configure(x = x * user_zoom)`
- Selection chrome → `canvas.move(dx_tick)` in physical pixels, and `winfo_rootx` for static bbox

On 1.0 × 1.25 canvas_scale vs. 1.0 user_zoom, the two place() paths disagree by a factor of 1.25. Tried `user_zoom` in drag too (v0.0.15.17 attempt); user reported the offset then scaled with drag distance instead of widget position, so neither formula gave a clean result.

The real question: does CTk's `ScalingTracker` DPI-scale `.place(x=N)` args when `SetProcessDpiAwareness(1)` is set? Two possibilities, each produces different-direction mismatch:
- CTk scales → `canvas_scale` overshoots, `user_zoom` matches
- CTk doesn't scale → `canvas_scale` matches, `user_zoom` lags

Neither matches user observation cleanly, so one of the assumptions (cursor delta calc, chrome move, or bbox read) is also off.

**Next step:** add temporary `print()` statements logging `canvas_scale`, `user_zoom`, `event.x_root delta`, `widget.winfo_rootx`, computed `new_x * factor`, after a single drag. Compare numbers against the cursor's actual screen position. Empirical numbers will say which formula matches reality — the code theory is inconclusive.

**Not blocking for now** — widget still usable, preview still correct, only the canvas visual during drag drifts. Revisit when a focused bug-hunting session is scheduled.

---

## ✅ CTkEntry — placeholder_text invisible on canvas

**Symptom:** dropping a fresh Entry or reopening a project showed a blank field on the builder canvas even though `placeholder_text` had a value. Exported `.py` ran fine — placeholder appeared there.

**Root cause:** `CTkEntryDescriptor.apply_state` was calling `widget.delete(0, "end")` unconditionally on every widget create. CTk's placeholder is literally the entry's text styled with `placeholder_text_color`, gated by the internal `_placeholder_text_active` flag. The blanket `delete()` wiped the placeholder text, and the flag never re-armed.

**Fix (v0.0.15.19):** early-return from `apply_state` when `initial_value` is empty — leave the widget untouched so CTk's post-init placeholder activation survives.
