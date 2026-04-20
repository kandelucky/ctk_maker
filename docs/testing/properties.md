# Area 3 — Properties panel

Every editor type, drag-scrub, conditional rows (`disabled_when` / `hidden_when`), grouped sections.

## Test

### Editor types
- [ ] **number** — typing, min/max clamp, dynamic max (e.g. corner_radius)
- [ ] **number ±1 spinner** — click step, hold auto-repeat, one undo per hold, min/max clamp (v0.0.15.7)
- [ ] **color** — type hex, picker dialog, swatch preview
- [ ] **color clear ✕** — clearable props commit clear_value on ✕ click; dimmed when already cleared (v0.0.15.9)
- [ ] **color "transparent" → "none" display** — value cell shows "none" when stored value is "transparent" (v0.0.15.9)
- [ ] **boolean** — checkbox toggle
- [ ] **string** — live commit on Enter / blur
- [ ] **multiline** — textarea with newline preservation
- [ ] **enum** — dropdown with icons (layout_type, stretch, grid_sticky, anchor)
- [ ] **anchor** — 3×3 grid click-to-pick
- [ ] **compound** — top / left / right / bottom
- [ ] **image** — browse / clear, file dialog
- [ ] **orientation** — horizontal / vertical (slider, progress)
- [ ] **font** — family / size / bold / italic / underline / strike / preview *(pending — dedicated font editor not built yet; `font_family` is plain string today, see TODO)*

### Drag-scrub
- [ ] Drag on number label → value changes live
- [ ] Alt = fine scrub (1px per unit)
- [ ] Commit as single undo entry on release
- [ ] Drag-scrub on W/H → widget resizes live
- [ ] Escape mid-drag cancels back to original value

### Conditional rows
- [ ] `disabled_when` — dependent row dims (e.g. border_width when border_enabled=false)
- [ ] `hidden_when` — dependent row vanishes (e.g. grid_rows on non-grid Frame)
- [ ] Toggle condition → rows re-appear / re-enable in-place, no rebuild flicker
- [ ] `layout_type` change rebuilds panel cleanly (Layout rows differ per manager)

### Grouped sections
- [ ] Group headers render with section titles
- [ ] Subgroups nested correctly (e.g. Character / Paragraph under Text)
- [ ] Paired rows side-by-side (X+Y, W+H, Size+BestFit)
- [ ] Padding / spacing consistent across widgets

### Selection / edit flow
- [ ] Click widget → panel loads its schema in <100ms
- [ ] Click different widget → panel rebuilds cleanly, no stale rows
- [ ] Multi-select from Object Tree → panel shows common props? or clears?
- [ ] Rename inline from Name field → Object Tree updates live
- [ ] Property change → canvas updates immediately
- [ ] Property change on hidden widget → model updates even though canvas skips

### Edge cases
- [ ] Very long property list (40+ rows) — scroll works
- [ ] Type invalid value (negative width, malformed hex) — rejects + restores
- [ ] Eyedropper across monitors — picks correct pixel *(verify — feature lives in external `ctk-tint-color-picker` library, not grep'd in our codebase)*
- [ ] Font preview with missing font — falls back gracefully *(pending font editor — see TODO)*

## Refactor candidates

- [ ] `panel.py` size audit — 1272 lines in one file; schema walker, editor dispatch, chrome builder, commit path, pickers all live together. Candidate split: `panel_schema.py` (populate_schema + pair/group traversal) and `panel_commit.py` (commit_prop + editor lifecycle)
- [x] ~~Editor registry — dispatch is if-chain?~~ — already a dict lookup in `editors/__init__.py` (`_EDITORS[ptype]`). Outdated note.
- [ ] `_populate_schema` filtering — 70-line while-loop does group / subgroup / pair state-tracking + hidden filtering inline. Could split the pair-collect and group-transition logic into helper generators.
- [ ] `_is_hidden` / `_compute_disabled_states` API asymmetry — one returns `bool` per-prop, the other returns a dict for the whole schema. Unify: both compute per-prop, caller iterates.
- [x] ~~Overlay management dedupe~~ — `OverlayRegistry` + named placers already unify the chrome (color / image / enum / pencil / number-spin / clear-button). Done.

## Optimize candidates

- [ ] `disabled_when` / `hidden_when` re-evaluates all lambdas on every keystroke — dep-map via `TrackingDict` to make it O(1) per change
- [ ] Full panel rebuild on `layout_type` change — could do surgical row add/remove
- [ ] Treeview row recreation during rebuild — profile flash / reflow

## Findings

- **[P3-1]** Drag-scrub ``<->`` cursor vanished after release when the mouse was still over the number-row label
  *Steps:* hover a numeric prop label → cursor flips to `sb_h_double_arrow` → drag to change → release without moving mouse → cursor resets to normal and stays normal; only clicking elsewhere + re-hovering restores `<->`.
  *Root cause:* `_on_release` cleared the tree cursor via `_set_cursor("")` but left `_cursor_mode` at `"drag"`; the next `<Motion>` saw `new_mode == self._cursor_mode == "drag"` and short-circuited before calling `_set_cursor("sb_h_double_arrow")` again.
  *Fix:* reset `_cursor_mode = ""` on release (v0.0.15.9) so the next hover triggers the cursor-change branch and re-applies `<->`.

- **[P3-2]** Object Tree right-click context menu rendered with embossed / double-shadowed text on Windows
  *Steps:* right-click any widget in the Object Tree → the popup menu labels look doubled (white foreground + slightly offset grey behind); most noticeable on the "Paste" and "Paste as child" rows when unavailable.
  *Root cause:* (a) `tk.Menu(self, ...)` where `self` was a `CTkFrame` child instead of the top-level Tk window — Windows native menu theme kicked in with a 3D border effect; (b) any `state="disabled"` menu entry triggers Windows' native "disabled emboss" rendering regardless of the flat `activeborderwidth=0` + `relief="flat"` style settings.
  *Fix:* (a) reparent the menu to `self.winfo_toplevel()` so the flat style sticks; (b) stop using `state="disabled"` — keep every entry at `state="normal"` and swap `foreground` colour to the disabled grey, with callbacks that no-op when the action can't run. Same pattern the top Edit menu already uses (`main_window._refresh_edit_menu_state`). v0.0.15.9.
