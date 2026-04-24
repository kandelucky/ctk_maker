# Observations — დაკვირვებები

> უცნაური behavior, რომელიც **ხელს არ გვიშლის**, მაგრამ ოდესმე შეიძლება რამე მოვიფიქროთ. "ეგებ ბაგია?"

---

## Verify builder on 100 % DPI display

The DPI canvas fix (v0.0.15.10) was written and tested on a 125 % DPI screen. On 100 % DPI `_dpi_factor` returns 1.0, so `canvas_scale` collapses to plain `value` and `Renderer.redraw` / `chrome.draw_for` / `_find_document_at_canvas` / drag motion should behave identically to pre-fix code.

Still worth sanity-checking on a real 96-DPI monitor: palette drop at exact position, drag within doc, drag across doc edge, resize, zoom ±, Layout Frame drop, cross-doc drag + Ctrl+Z.

If anything regresses, the DPI branch may need a guard that skips the scale multiplier entirely when `_dpi_factor <= 1.01`.

---

## Georgian keyboard input — IME bug

Known tkinter / Windows IME bug ([bpo-46052](https://bugs.python.org/issue46052)). Typing Georgian into a tk.Entry yields `?`. **Paste works; direct typing does not.**

Real fix requires a non-tkinter UI toolkit (PyQt6, Flet, wxPython). Not scheduled — CTk locks us to tkinter.

**Workaround in place**: `bind_all("<Control-KeyPress>")` routes by hardware keycode so Ctrl+V/C/X/A and Ctrl+S/N/O/W/Q/R keep working under Georgian/Russian layouts.

---

## `bg_color="transparent"` black-corner artifact

Tried syncing `widget.configure(bg_color=<effective parent bg>)` after every create/reconfigure plus walking up parent chain to resolve transparent ancestors. **Did not fix** the black-corner artifact on rounded widgets sitting directly on `tk.Canvas`.

Root cause is in CTk itself (`_detect_color_of_master` can't read a canvas background). User decided to accept visual artifact rather than keep patching. All workspace + schema changes reverted.

---

## CTk corner_radius limitation

CTk grows button to `text_w + 2*radius + padding`, so true small circles aren't possible with text — **preview = reality, exported code matches**. Not fixable at builder level.

---

## Color-level transparency

Tk only accepts 6-char `#RRGGBB`. 50% red text (e.g. `rgba(255,0,0,0.5)`) not possible natively.

**Workaround**: use image-based text with per-pixel alpha. PIL + CTkImage + CTkLabel respects PNG alpha (verified with `tools/test_transparent_png.py`).

---

## Eyedropper across monitors

Eyedropper feature lives in external `ctk-tint-color-picker` library. Multi-monitor behavior dependent on library internals. Not our code, can't fix here.

**If needed**: contribute upstream or replace picker.

---

## Font preview with missing font

Pending font editor implementation. Currently `font_family` is a plain string — user can type a missing font name and nothing warns them. Once font editor ships, missing-font fallback path needs a graceful default (Segoe UI / system default).

---

## How does the user use a Dialog?

**Question**: the builder lets the user Add Dialog (Form menu or workspace toolbar), edits both Main Window + Dialog side-by-side, and exports one `.py` with two classes (`MainWindow(ctk.CTk)` + `LoginDialog(ctk.CTkToplevel)`).

But **the exported `.py` does not actually open the dialog** — the commented instructions at the bottom (`# dialog = LoginDialog(app)`) leave the user on their own to figure out:
- Which button triggers which dialog?
- Where does the "wire a button to open dialog X" pattern fit?
- Modal (`grab_set`) vs modeless? Default?

Possible answers:
- **Docs page** — "Dialogs in CTkMaker": explains the commented pattern, shows one working example of a button opening a dialog in the exported code, notes modal / modeless
- **Widget-side "On click → Open Dialog" property** — CTkButton + a few other command-widgets gain a `Command Target` row (see the "widget-to-widget binding" idea) with a special option "Open Dialog: <dialog_name>". Exporter emits `button.configure(command=lambda: LoginDialog(app))`.
- **Wait** — deferring until the Variables + Event handlers phase where callbacks are first-class

Worth picking one before the first real user opens a project with a Dialog and gets confused.

---

## Duplicate of multi-selection only selects one result

**Inconsistency:**
- **Copy / Paste** of multi-selection → all pasted objects are selected together
- **Duplicate** (right-click → Duplicate) of multi-selection → only one duplicated object is selected

Expected: Duplicate should mirror Paste and select the full set of new objects.

**Fix candidate**: both paths end in `BulkAddCommand` — check that Duplicate path passes the full `new_ids` list to `project.set_multi_selection(ids, primary=...)` the way Paste does (see `object_tree_window.py` paste vs `workspace/core.py` duplicate).

---

## Selection state not tracked in undo/redo

Undo/redo reverts widget changes but doesn't restore the selection set that was active when the change was made.

**Example:**
1. Select widget A
2. Ctrl+click widget B (multi-select: [A, B])
3. Ctrl+click widget A (deselect: [B])
4. Ctrl+Z — reverts last property change, but selection stays as-is

**Expected** (maybe): selection should also roll back so Ctrl+Z returns to the `[A, B]` state, next Ctrl+Z to `[A]`.

**Why observation, not bug**: selection changes are cheap and user-controlled; treating them as undo steps would flood history with [select] entries. Worth design discussion before implementing — Figma/Photoshop don't track selection in undo either.

---

## Workspace stale drag after slow properties panel load

Defense guards in place (`event.state & 0x0100` in `_on_widget_motion`, `_drag = None` on press, `winfo_manager() == "place"` in `ZoomController.apply_to_widget`). Root cause retest pending — if stale drag no longer reproduces after v2 panel, guards stay as belt-and-suspenders.

**Status**: uncertain whether it still reproduces. Re-verify during next long session.
