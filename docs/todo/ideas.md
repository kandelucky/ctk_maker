# Ideas — მომავლის იდეები

> Exploratory. არ არის დაგეგმილი. თუ გადავწყვიტე გაკეთება, ფაზა გადადის [roadmap.md](roadmap.md)-ში.

---

## Major features

### Assets system — centralised project resources

Today every image reference is a raw filesystem path. Pain points:
- Moving project folder breaks images
- Export `.py` doesn't copy images
- No UI to browse / preview in-use assets
- Duplicate images load multiple times

**Proposal**: `assets/` folder alongside `.ctkproj` with copies of every resource (images, icons, fonts, CSV/JSON). New **Assets panel** (4th sidebar tab) with thumbnails + drag-to-canvas + drag-to-property. Import via Explorer drag (needs `tkinterdnd2`) or Import button.

Model: `project.assets: dict[asset_id → AssetEntry]` with `(relative_path, sha256, last_modified)`. Widget references become `asset:<asset_id>`. Export copies every used asset into `assets/` beside generated `.py` + rewrites paths to relative.

Touches: project model, exporter, palette UI, file I/O. Worth a dedicated Phase.

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

### Command Target — widget-to-widget value binding

CTkSlider, Switch, SegmentedButton, CheckBox, RadioButton, ComboBox, OptionMenu, Entry all accept `command=callable`. Simplest binding: `CTkSlider(command=progressbar.set)`.

**Schema side**: new `Command Target` row, new `widget_ref` ptype, dropdown from `project.iter_all_widgets()` filtered to `.set(value)` method owners. Store target node id in `node.properties["command_target"]`.

**Live preview**: workspace bridge callback, `source.configure(command=lambda v: target.set(v))` on property_changed or creation.

**Exporter**: two-pass (assign var names, then emit) so sibling refs resolve. Emit `source_var.configure(command=target_var.set)` after both constructed. New hook: `export_post_lines(cls, var_name, properties, node_to_var)`.

First candidates: CTkSlider (highest ROI), CTkSwitch, CTkSegmentedButton.

### Gradient button support

CTk has no native gradient fill. `background_corner_colors` only tints tiny padding area. Three paths:
1. **PIL-generated gradient image** + `CTkButton(image=..., compound="center", fg_color="transparent")`. Export must regenerate image at runtime.
2. **Custom `CTkGradientButton`** subclass overriding `_draw()`. ~150-200 lines, fragile across CTk versions.
3. **[tkGradientButton](https://github.com/Neil-Brown/tkGradientButton)** — plain tk, canvas stripes, no rounded corners. Wrong widget family, not CTk-compatible.

Pick whichever best preserves preview = reality.

---

## Smaller ideas

- **Font editor** — Inspector row for `font_family` with real picker (system list + search + preview sample). `tkinter.font.families()` source. Covers Area 3 test #11.

- **Frame right-click → Select All (children)** — multi-select every direct child. Mirrors Figma "Select All in Frame" + Photoshop "Select → Layer contents". Scope TBD: direct children or recursive.

- **Single-document export** — current exporter emits whole project. Add "Export current document…" menu / radio. Watch for cross-doc refs (shared colors, shared parent classes) — inline anything needed.

- **vbox / hbox child alignment inside parent** — per-child `align` enum → tk `pack(anchor=...)`. Qt Designer uses `QSpacerItem`, per-child anchor is simpler UX.

- **Drag PNG/JPG from Explorer → workspace** — needs `tkinterdnd2` (~200 KB). Worth trying once Assets panel lands.

- **Number editor input bg color** — `bg=VALUE_BG` (`#2d2d2d`) on inline tk.Entry doesn't visually change when constant edited. Treeview cell background likely covers it. Investigate then apply slightly lighter shade for number-type fields.

- **`fg_color="transparent"` picker option** — for image-only buttons, user has to type `"transparent"`. Add dedicated toggle/checkbox to color picker for discoverability.

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
