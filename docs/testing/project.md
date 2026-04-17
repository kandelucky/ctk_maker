# Area 5 — Project lifecycle

`.ctkproj` save / load, code export, preview, dirty tracking, recent files.

## Test

### New / Save / Load
- [ ] File → New — empty project with Main Window only
- [ ] Save new project — prompts for filename, saves
- [ ] Save again — no prompt, overwrites
- [ ] Save As — always prompts
- [ ] Load existing `.ctkproj` — all widgets + properties restored
- [ ] Recent files menu — ordered, latest first, missing files grey / removed

### Round-trip integrity
- [ ] Create complex project (nested frames, every layout type, 14 widgets, multi-document)
- [ ] Save → close → reopen — visually identical
- [ ] Diff saved JSON before and after round-trip — zero changes
- [ ] Save → undo → redo → save — no drift

### Legacy load
- [ ] v0.0.10 project (`pack` → `vbox` migration)
- [ ] v0.0.11 project (pack_fill / pack_expand → stretch)
- [ ] v0.0.12 project (grid_rowspan / columnspan stripped)
- [ ] v0.0.13 project loads cleanly into v0.0.14
- [ ] Corrupt JSON — rejects with clear error, doesn't crash

### Code export
- [ ] Export button / menu produces `.py`
- [ ] Generated `.py` runs with `python file.py`
- [ ] Runtime window matches canvas preview pixel-close
- [ ] Every layout_type produces correct tk call (`.place()` / `.pack()` / `.grid()` + `pack_propagate` + `grid_rowconfigure(uniform=...)`)
- [ ] Multi-document project exports multiple classes (one per doc)
- [ ] Image widgets reference files correctly
- [ ] No stray imports, no dead code
- [ ] Generated code passes basic pyflakes (no undefined names, no unused vars)

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

<!-- project / export bugs here -->
