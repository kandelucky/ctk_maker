# Area 5 — Project lifecycle

`.ctkproj` save / load, code export, preview, dirty tracking, recent files.

## Test

### New / Save / Load
- [x] File → New — empty project with Main Window only
- [x] Save new project — prompts for filename, saves
- [x] Save again — no prompt, overwrites
- [x] Save As — always prompts
- [x] Load existing `.ctkproj` — all widgets + properties restored
- [x] Recent files menu — ordered, latest first, missing files hidden (v0.0.15.16)

### Round-trip integrity
- [x] Create complex project (nested frames, every layout type, 14 widgets, multi-document)
- [x] Save → close → reopen — visually identical
- [x] Diff saved JSON before and after round-trip — zero changes
- [x] Save → undo → redo → save — no drift (dirty flag fix v0.0.15.18 makes marker match on undo-to-saved)

### Legacy load
- [ ] v0.0.10 project (`pack` → `vbox` migration) — skipped (no sample file on hand)
- [ ] v0.0.11 project (pack_fill / pack_expand → stretch) — skipped
- [ ] v0.0.12 project (grid_rowspan / columnspan stripped) — skipped
- [ ] v0.0.13 project loads cleanly into v0.0.14 — skipped
- [x] Corrupt JSON — rejects with clear user-facing error (v0.0.15.19)

### Code export
- [x] Export button / menu produces `.py`
- [x] Generated `.py` runs with `python file.py`
- [x] Runtime window matches canvas preview pixel-close
- [x] Every layout_type produces correct tk call (`.place()` / `.pack()` / `.grid()` + `pack_propagate` + `grid_rowconfigure(uniform=...)`)
- [x] Multi-document project exports multiple classes (one per doc)
- [x] Image widgets reference files correctly — `image_color` tint now routed through `_tint_image` helper (v0.0.15.17) so PIL tint survives export
- [x] No stray imports, no dead code
- [ ] Generated code passes basic pyflakes — not run (manual CE-2 runs the file; pyflakes is a separate check)

### Preview (Ctrl+R)
- [ ] Launches subprocess with current project
- [ ] Window appears correctly
- [ ] Close preview → main builder still responsive
- [ ] Unsaved changes — preview uses current state (not last save)

### Dirty tracking
- [ ] Fresh project — not dirty
- [ ] Any mutation → dirty flag on, title bar shows `*`
- [ ] Save → dirty cleared
- [ ] Undo to pre-first-change state → still dirty? (document behavior)
- [ ] Close project with unsaved changes → prompt (Save / Discard / Cancel)

### Edge cases
- [ ] Very large project (500+ widgets) — save time, load time
- [ ] Empty project — save works, load works, export produces minimal class
- [ ] File with unicode characters in path (Georgian / emoji)
- [ ] Read-only file — load works, Save As prompts, Save over shows error

## Refactor candidates

- [ ] `project_saver.py` + `project_loader.py` symmetry — keys written vs read match?
- [ ] `code_exporter.py` — layout emission scattered or centralised?
- [ ] Migration layer — each version's migration in its own function?
- [ ] Dirty tracking — manual flip in N places or centralised?

## Optimize candidates

- [ ] JSON size on disk — can shrink by omitting defaults?
- [ ] Load time for large projects — JSON parse vs WidgetNode rebuild
- [ ] Save time — hopefully dominated by disk I/O; if not, serialize faster
- [ ] Export output line count — readable but not bloated?

## Findings

- **[P5-1]** History from previous project survived File → Open → Ctrl+Z after load resurrected widgets from the closed project
  *Fix:* `project_loader.load_project` now calls `project.history.clear()` right after `_clear_existing_widgets` (v0.0.15.16).

- **[P5-2]** Recent Projects listed files that no longer exist on disk — clicks showed a generic "Open failed" dialog
  *Fix:* Startup dialog dims the row + shows "missing" label, disables click; File menu Recent Forms hides them entirely. The path stays in `recent.json` in case the drive is temporarily offline (v0.0.15.16).

- **[P5-3]** Corrupt / wrong-version project file surfaced raw technical JSON errors to end users
  *Fix:* `ProjectLoadError` messages rewritten in plain language with file name, hint about handcraft / interrupted save / version mismatch (v0.0.15.19).

- **[P5-4]** Dirty flag stayed ON after Ctrl+Z undid every change back to the saved state — title kept the `•` marker and prompted an unneeded save
  *Fix:* Dirty tracking rerouted through a history-top marker (``_saved_history_marker``); `_recompute_dirty` compares the current undo top to the saved marker so undo-to-saved flips the flag off automatically (v0.0.15.18).

- **[P5-5]** Exported app title read `Main Window` — misleading since the field is both the window display name AND the runtime `self.title(...)`
  *Fix:* Default document name now tracks the project name (`Untitled` until the New dialog sets a real one). `clear()` syncs on reload as well (v0.0.15.19).

- **[P5-6]** hbox / vbox grow children stuck at their pre-split size when a new grow child joined the row — 1st button kept full width, 2nd got half
  *Fix:* `_apply_grow_equal_split` now configures every grow sibling on each re-apply, not just the `anchor_widget` being reapplied (v0.0.15.17).

- **[P5-7]** `image_color` tint applied in the builder was lost on export — the runtime app rendered the raw PNG colour
  *Fix:* `code_exporter` emits a `_tint_image(path, hex, size)` helper when any widget has a tint set, and `_image_source` routes through it. One PNG, unlimited colour variants at runtime (v0.0.15.17).
