# Ideas — მომავლის იდეები

> Exploratory. არ არის დაგეგმილი. თუ გადავწყვიტე გაკეთება, ფაზა გადადის [roadmap.md](roadmap.md)-ში.

---

## Major features

### Dialog → reusable composite

Convert an existing Dialog document into a **portable composite object** that can be dragged into another window's canvas as a single group — preserving the full widget tree, properties, layout, and relative positions.

Think of it as "wrap this Dialog's contents into a re-usable Frame subtree." After the conversion:
- The Dialog's root-level widgets become children of a new container Frame
- The Frame can be dropped into any window / dialog / Frame
- Optionally: the original Dialog document can be deleted (subtree promoted elsewhere) OR kept as a template

**Two flavours worth comparing:**

1. **One-shot "Extract contents to Frame"** — right-click a Dialog → "Extract to Frame…". Pick a target window. A new container Frame appears in that window holding every top-level widget from the dialog. Names, properties, layout all preserved. The source dialog is left empty (or deleted on confirmation). Simplest.

2. **Template / composite library** — the Dialog is "saved as composite" and appears in a new palette category. Drag-drop as a whole. Closer to Figma components / Qt promoted widgets. Ties into the Prefab idea below — same storage, same UX, just sourced from a Dialog instead of a free selection.

Goal is to let the user build complex sub-panels (login form, settings row, nav bar) in the spacious Dialog canvas and then snap them into the real app window once they're happy. Avoids having to lay out a deeply nested form inside the main window's cluttered canvas.

### Prefabs / reusable widget composites

Today every form is built from scratch. Typical apps have dozens of form rows with same 3-widget shape (`label + entry + ✕ button`, `icon + text + chevron`).

**Proposal**: select widgets → "Save as Prefab" → drop from new **Prefab Box** palette tab.

Two modes worth comparing:
- **Copy-mode** — each drop clones subtree, edits affect only that instance (Figma "detached component"). Simpler.
- **Reference-mode** — instances linked to source, editing source propagates. Harder: detach, rename propagation, conflict on overrides.

Start with copy-mode. Storage: `prefab_<name>.ctkpf` = pruned `.ctkproj` subtree. UI: Palette `Prefabs` category, right-click widget → "Save as Prefab…", metadata panel (rename/delete/"Update from instance").

Dovetails with Assets phase — Prefab Box + Asset Box turns builder into "design-system editor".

### Python import — `.py` → editable project

Reverse of `code_exporter`. Three tiers by effort:

**Tier 1** — round-trip our own exports (easy). AST parser recognising `code_exporter.generate_code` output only. File → Open Python menu.

**Tier 2** — arbitrary `.place()`-based CTk code (medium). Handle helper variables, `class App(ctk.CTk)`, drop callbacks/lambdas/loops with warnings. `CTkFont(...)` / `CTkImage(...)` re-extract.

**Tier 3** — grid / pack layouts (hard, depends on layout managers complete). Round-trip `.grid(...)` / `.pack(...)` calls. Success criterion: open CTk's `examples/complex_example.py` + `examples/image_example.py`.

**Alternative** — side-by-side reference viewer (no import): "Open in VSCode" button on CTk reference entries. Pattern already in `docs/architecture_dashboard.html`.

### Workspace without runtime interactivity

Currently every canvas widget is a full live CTk instance — buttons run hover-fade, sliders drag, switches toggle. Distracts from layout work.

**Proposal**: render canvas widgets as **static visual proxies** — same shape/fill/border/text/font/image, no event handlers/hover/focus/animations. Preview (Ctrl+R) still covers behavioural sanity.

Two paths:
- **(a) disable hover at source** — wrap `create_widget` to pass `hover_color=fg_color` + bind `<Enter>` returning "break". Cheap, reversible. Doesn't kill click/focus.
- **(b) draw as canvas primitives** — rectangle + text + image canvas items per widget. Matches Qt Designer's proxy model exactly. Big refactor.

Start with (a), revisit (b) if hover suppression isn't enough. **Permanent design-mode behavior**, not togglable.

### Behavior / runtime methods — three options to make Preview live

Currently Preview (Ctrl+R) shows a static UI — buttons don't trigger anything because the builder has no place to declare callbacks / variables / event handlers. Three competing approaches to fix that:

**A. Inspector "Click action" property (cheapest)**

Per-widget multiline `command_code` field in the Inspector. User types a Python snippet:
```
print("submit clicked")
self.label_1.configure(text="done!")
```
Generator emits `button_1.configure(command=lambda: (...))` (or a named method). Preview uses the same generator, so click works in-builder.

- Pros: one schema row per click-able widget, ~1 day to implement, immediate value.
- Cons: callbacks only — no shared state, no `StringVar`s, no `validate=`.

**B. Behavior panel (most flexible)**

A new "Behavior" tab next to the palette. User writes a single Python file:
```python
def setup(window):
    window.button_1.configure(command=lambda: print("clicked"))
    window.entry_1.bind("<Return>", lambda e: do_thing())
```
Generator and Preview both call `setup(self)` after widget creation.

- Pros: any behavior — variables, validation, custom logic, multi-widget glue. Matches Qt Designer's pattern.
- Cons: needs an in-builder code editor (syntax highlight, error reporting, save with project), assumes the user knows Python, several weeks of work.

**C. Visual binding (already listed below — Command Target)**

See *Command Target — widget-to-widget value binding*. Drag-and-drop wire-up of `slider.command → progressbar.set`, no typed code. Strong for the patterns it covers, weak for "custom logic".

**Decision deferred** — pick after asset system + dedicated dialogs land. Likely path: A first (cheap win, makes Preview less of a fiction), then B+C together for the polished v1.0 story.

**TODO — audit per-widget runtime methods first.** Every CTk widget exposes its own set of runtime methods beyond what Inspector covers (Entry: `.get()` / `.insert()` / `.delete()` / `.bind()` / `.icursor()` / selection ops; Textbox: same plus `tag_*`; Slider: `.get()` / `.set()`; SegmentedButton: `.set()` / `.get()` / `.insert()` / `.delete()` / `.configure(values=…)`; Tabview: `.add()` / `.delete()` / `.tab()` / `.set()` / `.get()`; etc.). Read each widget's official doc, list all runtime-callable methods + bindable events per descriptor, and decide which deserve first-class builder support (Behavior panel autocomplete, Command Target endpoints, code-snippet template hints) vs. which stay "exported `.py` only". Reference: `https://customtkinter.tomschimansky.com/documentation/widgets/<widget>` for each.

### Command Target — widget-to-widget value binding

CTkSlider, Switch, SegmentedButton, CheckBox, RadioButton, ComboBox, OptionMenu, Entry all accept `command=callable`. Simplest binding: `CTkSlider(command=progressbar.set)`.

**Schema side**: new `Command Target` row, new `widget_ref` ptype, dropdown from `project.iter_all_widgets()` filtered to `.set(value)` method owners. Store target node id in `node.properties["command_target"]`.

**Live preview**: workspace bridge callback, `source.configure(command=lambda v: target.set(v))` on property_changed or creation.

**Exporter**: two-pass (assign var names, then emit) so sibling refs resolve. Emit `source_var.configure(command=target_var.set)` after both constructed. New hook: `export_post_lines(cls, var_name, properties, node_to_var)`.

First candidates: CTkSlider (highest ROI), CTkSwitch, CTkSegmentedButton.

### FX Button — Unity-style multi-state tint button

A new custom widget (NOT a CTk modification) that mimics Unity UI Button's Color Tint transition: smooth animated colour interpolation between Normal / Highlighted / Pressed / Disabled states. Lives on the experimental `fx-button-experiment` branch, paused mid-iteration.

**Mental model finalised on 2026-04-22:** FX Button is **not** a generic container — it does not accept arbitrary dragged children. It's a **self-contained atomic widget** that manages its own internal Text and Image elements via Inspector toggles:

```
Inspector (FX Button):
  Geometry / Rectangle / Button Interaction / Main Colors  ← shape only
  Text:
    Show Text         [✓]            ← boolean toggle
    Text              "Submit"       ← multiline (visible when Show Text=on)
    Font / Color / etc.
    Layout            Auto-fit / Free
    X, Y, W, H        ← Free mode only; clamped to button bounds
  Image:
    Show Image        [✓]
    Image             [picker]
    Image Color       (tint, clearable)
    Layout            Auto-fit / Free
    X, Y, W, H        ← clamped to button bounds
```

Drag/copy-paste/duplicate of arbitrary widgets INTO the FX Button — **disallowed**. Object Tree shows it as a single node, internal text/image are hidden implementation detail.

**Phase 1 — Inspector cleanup** (✅ done, on branch)
- Strip text/font/image/anchor/compound/preserve_aspect/border_spacing rows from descriptor; expose only Geometry, Rectangle, Button Interaction, Main Colors
- Force `text=""` in defaults so CTk's "CTkButton" fallback doesn't leak into preview
- Palette ghost colour pulls from descriptor's `default_properties["fg_color"]` (so dragged FX Button shows purple `#8b5cf6`, not the generic blue)

**Phase 2 — Show Text / Show Image internals** (next)
- Add `text_visible` / `image_visible` booleans + sub-properties (text/font/colour/layout-mode/x/y/w/h, image/colour/layout-mode/x/y/w/h)
- `apply_state` creates / removes internal `CTkLabel` children placed via `place()` with coords clamped to the button's box
- Auto-fit mode → fill the button (CTkButton's classic text behavior). Free mode → user-positioned, bounded.
- Internals are owned by the descriptor — not visible in Object Tree, not draggable, not copy-pastable

**Phase 3 — Animation (Unity Color Tint)**
- Custom `CTkFXButton(ctk.CTkButton)` subclass replaces direct `CTkButton` runtime
- New params: `highlighted_color`, `pressed_color`, `disabled_color`, `fade_duration_ms` (default 100ms, matches Unity)
- Bindings: `<Enter>` / `<Leave>` / `<ButtonPress-1>` / `<ButtonRelease-1>` → animated colour interpolation
- Animation: `after(16ms, _step)` loop, RGB linear blend across `fade_duration_ms / 16` frames; configure background + tint internal text/image children
- **Performance:** pre-compute tinted CTkImage variants once at widget creation (4 states), swap on transition — no per-frame PIL work. Editor canvas honours a `design_mode` flag to disable animation entirely (matches the "Workspace without runtime interactivity" idea).

**Phase 4 — Exporter integration**
- Generator detects FX Button presence → emits the `CTkFXButton` class source once at the top of the generated `.py` (inline injection, exported file stays self-contained — no extra `pip install` for end user)
- Preview already uses the same generator, so animation works in-builder
- The internal text/image children get emitted as `self.{var}_text` / `self.{var}_image` Labels parented to the FX Button

**Phase 5 — Future polish**
- OnClick handler (ties into the "Behavior / runtime methods, option A" idea above)
- Selected colour for focused state (Tab navigation)
- Other Unity-style transition modes (Sprite Swap, Animation) — only if needed

**Tkinter limit accepted:** rotation is impossible (tk widgets are axis-aligned only). True alpha overlay layers are also unavailable — colour transitions use pre-computed blends instead. Both noted on 2026-04-22.

**Status (2026-04-22):** Phase 1 complete on `fx-button-experiment` branch. Phase 2 work paused — `main` returns to v0.0.15.19 stable Area 7 fixes. Resume when current focus (Area 7 + asset system) wraps. Naming TBD ("FX Button" / "Tinted Button" / "Reactive Button").

### Gradient button support

CTk has no native gradient fill. `background_corner_colors` only tints tiny padding area. Three paths:
1. **PIL-generated gradient image** + `CTkButton(image=..., compound="center", fg_color="transparent")`. Export must regenerate image at runtime.
2. **Custom `CTkGradientButton`** subclass overriding `_draw()`. ~150-200 lines, fragile across CTk versions.
3. **[tkGradientButton](https://github.com/Neil-Brown/tkGradientButton)** — plain tk, canvas stripes, no rounded corners. Wrong widget family, not CTk-compatible.

Pick whichever best preserves preview = reality.

---

## Smaller ideas

- **Hover affects text + image, not just background** — CTk's hover effect changes only `fg_color → hover_color`; text colour and image tint stay fixed. Add two new Inspector colour rows on CTkButton: `text_hover_color` + `image_hover_color`, both clearable (cleared = "stay the same on hover"). Builder + exporter wire `<Enter>`/`<Leave>` bindings on the button: `<Enter>` swaps `text_color` to `text_hover_color` and re-tints the CTkImage, `<Leave>` restores. Both Preview and exported `.py` use the same emit path. Mostly valuable for icon-only / icon+label buttons where the icon should darken on hover. Trade-off: exported code grows by ~10 lines per affected button (helper + bind block).

- **Font editor** — Inspector row for `font_family` with real picker (system list + search + preview sample). `tkinter.font.families()` source. Covers Area 3 test #11.

- **Frame right-click → Select All (children)** — multi-select every direct child. Mirrors Figma "Select All in Frame" + Photoshop "Select → Layer contents". Scope TBD: direct children or recursive.

- **Single-document export** — current exporter emits whole project. Add "Export current document…" menu / radio. Watch for cross-doc refs (shared colors, shared parent classes) — inline anything needed.

- **vbox / hbox child alignment inside parent** — per-child `align` enum → tk `pack(anchor=...)`. Qt Designer uses `QSpacerItem`, per-child anchor is simpler UX.

- **Drag PNG/JPG from Explorer → workspace** — needs `tkinterdnd2` (~200 KB). Worth trying once Assets panel lands.

- **Number editor input bg color** — `bg=VALUE_BG` (`#2d2d2d`) on inline tk.Entry doesn't visually change when constant edited. Treeview cell background likely covers it. Investigate then apply slightly lighter shade for number-type fields.

- **`fg_color="transparent"` picker option** — for image-only buttons, user has to type `"transparent"`. Add dedicated toggle/checkbox to color picker for discoverability.

- **Run `.ctkproj` via Run Python Script…** — extend the launcher so picking a `.ctkproj` transparently loads the project, regenerates code in-memory via `generate_code()`, writes a temp `.py`, and runs it as a subprocess. No format change needed — the `.py` is deterministic from the project data so embedding it in the file would just duplicate state. Temp file lives in `%TEMP%`, optionally persist-for-debug setting.

- **Rename `.ctkproj` extension** — current name is ad-hoc (`ctk` + `proj`). Pick a cleaner name before v1.0 public release. Candidates: `.ctkb` (builder), `.ctkui`, `.ctkform` (Qt Designer parallel — `.ui`). Needs: save/load path update, filedialog filters, recent-files migration for existing `.ctkproj` files, docs pass.

- **Preview window — modal lockout + always-on-top** — when `Ctrl+R` (or per-dialog ▶) launches a preview, the builder should freeze until the preview window closes, and the preview should stay above every builder window. Two pieces:
  - Topmost: post-process the temp `preview.py` (don't touch the user's exported `.py`) — replace `app.mainloop()` with `try: app.attributes('-topmost', True)` + `app.mainloop()`.
  - Lockout: `self.attributes("-disabled", True)` on Windows + poll the subprocess every ~500 ms via `after`; restore on exit. Cross-platform fallback (Linux/X11 may need `iconify` instead of `-disabled`). Apply to both main and per-dialog preview launches.
  - Skipped on first pass (2026-04-22) because the cross-platform path turned out fiddlier than expected.

- **Templates / Presets** for common windows (login form, settings dialog, wizard).

- **Variables panel** (StringVar, IntVar, BooleanVar — create + bind). Complementary to Command Target.

- **Event handlers** (generate command callbacks).

- **Project settings** (Python version, theme, output structure).

- **Plugin system** for new widget types.

---

## Comparisons / competitive notes

### PyUIBuilder comparison

PaulleDemon/PyUIBuilder is the closest competitor (2.3k stars, JavaScript/Electron, multi-framework: Tkinter + CustomTkinter + WIP Kivy/PySide).

**His paid ($29-49) premium features — all free in this project**: save/load project files, dark theme, live preview, commercial use.

**His advantages**: multi-framework output, flex/grid layout managers, web-based distribution, ProductHunt + Discord ecosystem, `requirements.txt` generation, 3rd party plugin system.

**Our advantages**: **preview = reality** (we ARE a CTk app, not a JS approximation), native font scaling with zoom, real PNG alpha rendering, deep CTk integration via descriptor pattern (`transform_properties`, `derived_triggers`, `disabled_when`), Object Tree with multi-select + visibility/lock + drag-reparent, custom color picker with tint strip + saved colors, Georgian UI + i18n readiness, no Electron overhead.

**Positioning**: *"CustomTkinter's native Qt Designer — free, open source, always authentic preview"*.
