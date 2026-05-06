# Export Test Plan

**Status:** ready to execute
**Goal:** prove the export pipeline correctly translates every widget, variable, layout, handler, and reference into runnable Python that does what the design said it would do — with minimal, idiomatic generated code.

## Strategy — three layers

| Layer | Coverage | When to use | Effort |
|---|---|---|---|
| **A. Smoke** | Pipeline-level — does export run end-to-end? | First, every change | ~1 hour |
| **B. Per-widget matrix** | Each widget's emit + properties | Before launch | ~1-2 days |
| **C. Edge cases + code quality** | Multi-window, assets, handlers, refs, idempotence | Before launch | ~1 day |

**Total realistic budget:** 2-3 days for full pre-launch run. Smoke pass alone: 1 hour.

## Layer A — Smoke (3 projects)

Three minimal projects that together exercise every Phase of the export pipeline. If any of these break, stop and fix before going deeper.

| Project | What it covers |
|---|---|
| **Login** | Phase 0 (descriptions) + Phase 1 (StringVar bindings) + Phase 2 (button handler) + Object References |
| **Slider Demo** | Phase 1.5 (IntVar live binding `textvariable=`/`variable=`) + Slider's `command` handler emitting `(self, value)` signature |
| **Multi-window Settings** | Phase 1.5 (Toplevel reading `self.master.var_X`) + Phase 2 (cross-window handler) + Window-scope global Object Reference |

For each:
1. Build in GUI (user creates empty page, then drags widgets OR Claude writes a `build_<name>.py` script per `reference_ctkmaker_project_scripting.md`)
2. Export from File → Export
3. Run exported `.py` via `subprocess` (per `feedback_test_exports_yourself.md`)
4. Read generated code line by line — flag anything non-minimal or unexpected
5. Any bug → 30-second GitHub Issue, then continue

## Layer B — Per-widget matrix

21 palette entries × representative configurations. One page per widget (or group of related widgets), each with multiple variants showcasing the widget's surface.

The existing **New Showcase 2** project is the natural test bed — Buttons page already shipped, the rest are queued. Building those pages IS the test.

### Per-widget checklist

Per widget, verify the export produces correct code for:

| Aspect | What to check |
|---|---|
| Constructor kwargs | Every property in `default_properties` round-trips correctly to CTk constructor |
| Default-skip | Properties matching CTk's own defaults are NOT emitted (keeps output compact) |
| `_NODE_ONLY_KEYS` | Builder-only keys (`x`, `y`, `width`, `height`, `image_width`, `image_height`, etc.) stripped from kwargs, only used in `place()` / `CTkImage` size |
| Special handling | `font_*` → `ctk.CTkFont(...)`, `image` → `ctk.CTkImage(...)`, `state_disabled` → `state="disabled"`, etc. |
| `apply_state` post-construct | `.set(...)`, `.select()`, `.insert(0, ...)` lines emit AFTER constructor + `place()` |
| `recreate_triggers` | Properties marked `recreate_triggers: True` produce correct constructor (e.g. `CTkProgressBar` orientation flip) |
| Layout container child placement | When inside vbox/hbox/grid parent: `pack(side=..., fill=..., expand=...)` or `grid(row=..., column=..., sticky=...)` |
| `prefers_fill_in_layout` default | Auto-fill widgets (Button, Entry, Label, Frame, ...) emit `stretch="fill"` / `sticky="nsew"` defaults |

### 21 palette entries — group by phase contribution

| Group | Widgets | Distinguishing emit features |
|---|---|---|
| **Layouts** | Vertical Layout, Horizontal Layout, Grid Layout | All share CTkFrame descriptor with `layout_type` preset → emit `pack`/`grid` calls instead of `place` for children |
| **Buttons** | Button, Segmented Button | Custom `CircleButton` class (inlined into export). Segmented Button uses `multiline_list_keys={"values"}` → list emit |
| **Display** | Label, Image, Card, Progress Bar, Circular Progress | Image = builder composite (`CTkLabel(text="", image=...)`). Card = composite (`CTkFrame` + inner label via `export_state`). CircularProgress = `is_ctk_class=False` (inlined into export) |
| **Selection** | Check Box, Radio Button, Switch | All have `BINDING_WIRINGS` entries → variable kwargs |
| **Input** | Entry, Textbox, Combo Box, Option Menu, Slider | ComboBox/OptionMenu need `scrollable_dropdown.py` sidecar. Entry's `initial_value` → textvariable (Phase 1.5 special-case) |
| **Containers** | Frame, Scrollable Frame, Tab View | Scrollable Frame composite (outer wrapper). Tab View uses `parent_slot` for child routing |

## Layer C — Edge cases + code quality

### Variable matrix (full coverage of binding semantics)

| Test | Setup | Expected emit |
|---|---|---|
| Global StringVar bound to Label.text | 1 var, 1 label | `self.var_X = tk.StringVar(...)` on main class, `textvariable=self.var_X` kwarg |
| Local StringVar bound to Label.text in same doc | 1 local var, 1 label | Same shape, but on document's class (Toplevel form) |
| Toplevel reads global var | Global var + Toplevel | `self.master.var_X` reference, NOT new declaration on Toplevel |
| Multi-radio group (3 radios share IntVar) | 1 IntVar, 3 RadioButtons each with unique `value=` | Single var declaration, each radio gets `variable=self.var_X, value=N` |
| Slider IntVar two-way sync | 1 IntVar, Slider + Label both bound | `variable=` on slider, `textvariable=` on label, single var instance |
| Switch BooleanVar | 1 BooleanVar, 1 Switch | `variable=self.var_X` |
| CheckBox + Switch on same BooleanVar | 1 BooleanVar, 1 CheckBox, 1 Switch | Both wire to same var; sync at runtime |
| Cosmetic binding (`fg_color` → StringVar) | Var without BINDING_WIRINGS entry | Emits literal value at create time, NOT `textvariable=`. Auto-trace helper if `_emit_auto_trace_bindings` triggers |
| Bound to deleted variable | Manually delete the var while binding exists | Property stripped; descriptor falls back to default value |
| Variable rename | Rename var, re-export | All bindings update; exported code uses new name |
| Variable name collision with reserved keyword | Set name to `class` or `def` | Sanitize to fallback like `_class_ref` (per `_resolve_var_names`) |

### Handler matrix

| Test | Setup | Expected emit |
|---|---|---|
| Single command handler | Button → 1 method | `command=self._behavior.method` |
| Multi-method command | Button → 3 methods | `command=lambda: (self._behavior.m1(), self._behavior.m2(), self._behavior.m3())` |
| `bind:<Return>` on Entry | Entry → on_return | `self.entry.bind("<Return>", self._behavior.on_return, add="+")` |
| Multi-bind on same event | Entry `<Return>` → 2 methods | Two repeated `.bind(...)` calls, both with `add="+"` |
| Mixed command + bind on same widget | Button with `command` + `bind:<Button-3>` | Both styles emitted independently |
| Handler points at missing method | Bind to method not in `.py` | Exporter strips it (filtered by `_filter_handlers_to_existing_methods`); appears in `get_missing_behavior_methods()` post-export |
| Slider `command` signature | Slider → on_change | Method stub uses `(self, value)`, command kwarg = `self._behavior.on_change` |
| ComboBox/OptionMenu select callback | OptionMenu → on_select | Same `(self, value)` signature |

### Object References matrix

| Test | Setup | Expected emit |
|---|---|---|
| Local widget ref bound to button | 1 local ref `submit_btn` → button widget | `self._behavior.submit_btn = self.button_X` after `_build_ui()` |
| Local ref unbound | Ref declared without target | Skipped silently (no emit line) |
| Global Window ref | Global ref `main_win` → main document | `self._behavior.main_win = MainWindow` (class symbol) |
| Global Dialog ref from main window | Global ref → Dialog | Class symbol resolved via `_DOC_ID_TO_CLASS` |
| Cross-doc reference (single-doc export) | Global ref to Dialog, only main doc exported | Skipped — target not in this export |
| Reference name collision with widget name | Both widget and ref named `submit` | One gets `_2` suffix (sanitization in `_resolve_var_names`) |

### Layout managers

| Test | Setup | Expected emit |
|---|---|---|
| `place` (default) | Window with widgets at absolute coords | `widget.place(x=..., y=..., width=..., height=...)` |
| `vbox` (Vertical Layout) | Frame with `layout_type="vbox"`, 3 children | `widget.pack(side="top", fill=..., expand=..., padx=..., pady=...)` |
| `hbox` (Horizontal Layout) | Frame with `layout_type="hbox"` | `widget.pack(side="left", ...)` |
| `grid` (Grid Layout) | Frame with `layout_type="grid"`, 2×2 children | `widget.grid(row=..., column=..., sticky=..., padx=..., pady=...)` |
| Pack-balance helper emit | Project mixes `vbox` + `place` siblings | Helper emitted only when `_project_needs_pack_balance` returns True |
| Stretch="fill" auto-default | Layout-aware widget dropped into vbox | `expand=True, fill="both"` for `prefers_fill_in_layout` widgets |
| Tabview child routing | CTkTabview with widgets in tab "Settings" | Children attached to `widget.tab("Settings")`, NOT widget itself |
| Nested ScrollableFrame | Widget inside CTkScrollableFrame | Children in `widget._scrollable_frame` (or whatever the inner master is) |

### Window properties

| Test | Setup | Expected emit |
|---|---|---|
| Default window | 800×600, resizable both | `self.title("...")`, `self.geometry("800x600")`, `self.resizable(True, True)` |
| Frameless | `frameless=True` | `self.overrideredirect(True)` |
| Locked size | `resizable_x=False, resizable_y=False` | `self.resizable(False, False)` |
| Custom fg_color | `fg_color="#1e1e1e"` | `self.configure(fg_color="#1e1e1e")` or constructor kwarg |
| Default fg_color (transparent) | Default | NOT emitted (default-skip) |

### Asset handling

| Test | Setup | Expected behavior |
|---|---|---|
| Image asset reference | Widget with `image=asset:images/avatar.png` | Generated code: `image=ctk.CTkImage(light_image=Image.open(...), size=(W, H))`. Path resolves to `assets/images/avatar.png` next to the export |
| Asset folder copy | Export project with images/fonts | `assets/` folder appears next to `.py` with same structure |
| Asset filter (per-page export) | Export single page | Only assets referenced by THAT page get copied |
| Behavior subtree copy | Export with handlers | `assets/scripts/__init__.py` + `assets/scripts/<page>/` chain copied |
| Custom font asset | Project uses `assets/fonts/Inter.ttf` | Generated code uses `tkextrafont` to register; `_project_uses_custom_fonts` triggers helper |
| ScrollableDropdown sidecar | Project has CTkComboBox or CTkOptionMenu | `scrollable_dropdown.py` copied next to export |
| Lucide icon | Button with `image=asset:icons/save.png` | Same as image asset |
| Missing asset (broken token) | Token points at deleted file | Export still produces valid Python; runtime falls back gracefully |

### Multi-document / Toplevel

| Test | Setup | Expected emit |
|---|---|---|
| Single doc | Just main window | One class, `__main__` block at end |
| Main + Dialog | Main window + 1 Toplevel | Two classes; Dialog accessed via `Dialog(self)` from main's behavior |
| Main + 3 Dialogs | Multiple Toplevels | Three Dialog classes, each separate |
| Toplevel-only export | Export single Toplevel as standalone | `force_main=True` flattens its globals to locals; emits as `class X(ctk.CTk)` not `ctk.CTkToplevel` |
| Doc with handlers but no widgets | Empty doc with behavior file | Behavior class instantiated, `setup()` called even though `_build_ui()` is empty |
| Doc with refs but no handlers | Object refs only, no widget events | Behavior class still instantiated for the ref slots |

### Code quality

| Check | How |
|---|---|
| **Runnable** | `subprocess.run([sys.executable, exported.py])` exits 0 |
| **No syntax errors** | `py_compile.compile(exported.py, doraise=True)` |
| **Idempotent export** | Export same project twice → byte-identical output (or diff is whitespace-only) |
| **Round-trip stable** | Save → load → export → save → load → export = same final output |
| **Minimal output** | Default-matching kwargs absent. Compare line count to a manual-written equivalent — within 10% |
| **Readable** | Identifiers match user's widget names where valid (per `_resolve_var_names`) |
| **No dead imports** | Every import statement is used |
| **No spurious whitespace** | No trailing whitespace, exactly one blank line between class definitions |
| **Header stamp** | `# Generated by CTkMaker v<version>` line at top |
| **Cross-Python-version** | Runs on 3.10 / 3.11 / 3.12 / 3.13 / 3.14 (sample if all available) |

### Bundle / .zip export

| Test | Setup | Expected behavior |
|---|---|---|
| `as_zip=True` | Same project, zip output | `.zip` file at the chosen path; unzip → `.py` + `assets/` + helpers |
| Zip via runnable test | Unzip to fresh dir → `python <name>.py` | Runs without modification |

### Preview screenshot floater

| Test | Setup | Expected behavior |
|---|---|---|
| `inject_preview_screenshot=True` | F5 preview path | Orange ring + F12 button overlay; saving PNG works |
| Preview off (regular export) | Default | NO floater code in output |

## Layer D — Automated regression (post-launch)

A pytest test that builds a known fixture project programmatically, exports, and asserts on the resulting source. Lives in `tests/test_export_smoke.py`. Catches future regressions automatically.

```python
def test_login_smoke(tmp_path):
    # Build a Project with 2 entries + 1 button + 2 vars + 1 handler.
    project = build_login_fixture()
    out = tmp_path / "login.py"
    export_project(project, out)
    # Asserts:
    src = out.read_text()
    assert "self.var_username = tk.StringVar" in src
    assert "command=self._behavior.on_submit" in src
    assert py_compile.compile(out, doraise=True)
    # Smoke-run.
    subprocess.run([sys.executable, "-c",
                    "import importlib; importlib.import_module(...)"],
                   check=True)
```

Coverage budget: 5-8 fixture projects covering smoke + each Phase + each binding type + multi-doc. Runs in < 5 seconds. Worth ~1 day to build, pays back forever.

## Things you might have missed

Things from your description I'd add to the test:

| Addition | Why |
|---|---|
| **Round-trip + idempotence** | If save+load isn't stable, export drift between sessions. Hidden bug. |
| **Cross-Python-version** | You target 3.10+; users will run on whichever they have. Sample at minimum 3.10 + 3.13. |
| **Standalone runnability** | Verify export works in a venv with ONLY `customtkinter` installed (not CTkMaker). The exported code MUST NOT depend on CTkMaker. |
| **Asset path correctness** | When the user `cd`'s to the export dir and runs `python file.py`, all `asset:images/...` references must resolve. Test with a non-CWD execution. |
| **Default-skip correctness** | The biggest source of "ugly export" is over-emitting kwargs. Every widget should hit at least one variant where MOST kwargs are absent. |
| **Behavior file presence is sufficient** | Doc with handlers but no widgets must STILL get behavior class wired. Edge case. |
| **Reserved Python keywords as widget names** | User names a button `class` → must sanitize to `_class` or similar at export. |
| **Variable name fallbacks** | `get_var_name_fallbacks()` post-export — surface ANY rewritten name to the user. Test that it actually fires when expected. |
| **Missing behavior method** | Bind to method that doesn't exist in `.py` → must NOT crash export, must surface via `get_missing_behavior_methods()`. |
| **Component-inserted widget** | Drop `.ctkcomp` on canvas → those widgets must export correctly (variable migration, asset bundle, etc.). |
| **Frameless + transparent fg_color** | Together can cause window paint issues at runtime. Test the combo. |
| **`tk.Menu` widgets** | Not in palette but might appear via custom code — verify they don't break `disabledforeground` (per `feedback_tk_disabled_foreground.md`). |

## Recommended execution order

```
1. Layer A smoke (1 hour)
   ├── Login
   ├── Slider Demo
   └── Multi-window Settings
       └── If anything breaks → fix, restart from Layer A

2. Layer C edge cases — focus first on what users will hit most:
   ├── Variable matrix (1-2 hours)
   ├── Handler matrix (1-2 hours)
   ├── Object References (1 hour)
   └── Asset handling (1-2 hours)

3. Layer B per-widget matrix (1-2 days)
   ├── Reuse New Showcase 2 build pipeline
   ├── For each of 21 palette entries — build, export, run
   └── Layer B IS the showcase work — bundling

4. Code quality pass (half day)
   ├── Idempotence
   ├── Round-trip stability
   ├── Cross-Python-version sample
   └── Standalone venv test

5. Layer D regression suite (1 day, post-launch)
```

## Acceptance — pre-launch

Export testing complete when:

- [ ] All 3 smoke projects export and run cleanly
- [ ] Variable matrix: every entry passes
- [ ] Handler matrix: every entry passes
- [ ] Object References matrix: every entry passes
- [ ] Each of 21 palette entries has at least one tested variant
- [ ] Generated code passes `py_compile` for every test
- [ ] At least one test verifies standalone runnability (no CTkMaker installed)
- [ ] No `get_missing_behavior_methods()` or `get_var_name_fallbacks()` warnings on the smoke set
- [ ] All bugs filed → fixed or triaged
- [ ] At least 3 fixture-driven regression tests in `tests/test_export_smoke.py`

## What this plan does NOT cover

- CTk widget runtime correctness (we don't own CTkButton's behavior)
- Tk's pack/grid manager bugs
- User behavior code correctness
- Performance (large projects with 1000+ widgets)
- macOS / Linux runtime — flagged in README as Windows-only; punt to post-launch
- Visual / layout fidelity (preview-on-canvas vs exported-runtime equivalence) — eyeball check is enough; pixel diffing would be its own project

## Tracking

Bugs found go straight to GitHub Issues with the `export-test` label (30-second capture per `project_current_priorities.md` #2). Tracked separately from the test progress so the punch list stays clean.
