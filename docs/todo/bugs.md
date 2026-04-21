# Bugs — გასასწორებელი ბაგები

> რეალური bug-ები, რომელიც გვიშლის ხელს ან მოსალოდნელ behavior-ს არღვევს. პრიორიტეტი გასწორებაზე.

---

## 🐛 Selection chrome lags widget position

Two related symptoms — selection outline + resize handles don't track the widget accurately.

### A — Drag lag (few pixels behind)

**Reproduce:** Frame + Button inside. Select the Button → drag it slowly across the Frame → the selection outline + handles trail the widget by several pixels. When the drag stops, chrome snaps to the correct position.

**Hypothesis:** Selection chrome redraw runs on a throttled / deferred path (`_schedule_selection_redraw`) while drag motion updates the widget's position via `canvas.coords` / `place_configure` synchronously. The chrome catches up at idle, so high-frequency motion events leave it visually behind.

### B — "Teleport" mis-follow (property change mis-follow)

**Reproduce:** Widget at visible position, change `x` / `y` in Inspector to push it off-screen (scrolled-out area). The widget moves to the new location but the selection chrome **stays at the old visible position** — it never follows.

**Hypothesis:** The chrome redraw path doesn't update when the new position falls outside the visible canvas viewport, because bbox computation reads `winfo_rootx/rooty` which are only accurate for widgets currently mapped on-screen.

**Investigation for both:**
- Log `_schedule_selection_redraw` call sites vs actual paint tick
- Check `SelectionController._selected_bbox` behaviour when widget is outside the viewport
- Consider moving chrome updates into the same event path as position commits instead of deferred redraw
