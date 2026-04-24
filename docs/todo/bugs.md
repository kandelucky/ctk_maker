# Bugs — გასასწორებელი ბაგები

> რეალური bug-ები, რომელიც გვიშლის ხელს ან მოსალოდნელ behavior-ს არღვევს. პრიორიტეტი გასწორებაზე.

---

## ✅ Nested-widget drag — selection vs. widget visual mismatch on high-DPI

**Symptom (was):** dragging a widget inside a Frame on a 125 % / 150 % DPI screen, the selection outline tracked the cursor but the actual widget visual drifted. Worst at bottom-right of the parent; after release the widget stayed at the drifted position.

**Root cause (found v0.0.17):** CTk overrides `.place()` to apply DPI scaling via `_apply_argument_scaling`, but does **not** override `.place_configure()`. The initial placement in `_place_nested` went through `.place()` (scaled), while drag motion, `_handle_coord_prop` (release), and `apply_to_widget` used `.place_configure()` (unscaled). On the first drag tick the widget jumped from CTk-scaled coords to raw tk coords, offset by the DPI factor.

**Fix (v0.0.17):** unified every nested placement path on `.place(...)`. Drag motion, release property-change handler, and zoom apply-to-widget all now route through CTk's scaling wrapper.

---

## ✅ CTkEntry — placeholder_text invisible on canvas

**Symptom:** dropping a fresh Entry or reopening a project showed a blank field on the builder canvas even though `placeholder_text` had a value. Exported `.py` ran fine — placeholder appeared there.

**Root cause:** `CTkEntryDescriptor.apply_state` was calling `widget.delete(0, "end")` unconditionally on every widget create. CTk's placeholder is literally the entry's text styled with `placeholder_text_color`, gated by the internal `_placeholder_text_active` flag. The blanket `delete()` wiped the placeholder text, and the flag never re-armed.

**Fix (v0.0.15.19):** early-return from `apply_state` when `initial_value` is empty — leave the widget untouched so CTk's post-init placeholder activation survives.

---

## ✅ CTkScrollableFrame — editor/preview size mismatch

**Symptom (was):** a ScrollableFrame stored at 200×200 visually rendered at ~137×137 in the editor while a plain Frame at 200×200 looked correct. Preview also oversized SF by the scrollbar width (~14 px).

**Root cause (found v0.0.17):** two cooperating issues:
- Builder's composite canvas item used `zoom.value` (user_zoom only) for width/height while CTk scales widget geometry by `_apply_widget_scaling` (= user_zoom × DPI). Outer frame ended up pinned to raw `lw` px while plain Frame rendered at `lw × DPI`.
- Preview outer auto-grew by the scrollbar width because CTk's `width=` only sizes the inner canvas.

**Fix (v0.0.17):** `_place_top_level` + `_sync_composite_size` pin the canvas window using `canvas_scale` so SF matches a plain Frame at the same stored size on any DPI. `export_state` emits `._parent_frame.configure(width, height) + grid_propagate(False)` so the exported runtime matches the builder exactly. `_disable_container_propagate` now leaves SF's inner frame propagating so children pack naturally.

---

## Theme toggle (Light/Dark/System) — does not apply

**Symptom:** View → Appearance Mode (currently hidden/disabled) — switching between Light/Dark/System does not update the canvas, panels, or chrome. Currently hidden from the UI until the bug is fixed.
