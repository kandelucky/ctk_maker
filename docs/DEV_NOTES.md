# CTkMaker — Developer Notes

Internal conventions and references for working on CTkMaker itself (not for end users — see [spec/AI_CHEATSHEET.md](spec/AI_CHEATSHEET.md) for the user-facing prompt material).

## Launch

```
cd C:\Users\likak\Desktop\ctk_maker
python main.py
```

Or via `run.bat`. **Do NOT** use `python -m app` — `app` is a package without `__main__.py`, so module-style launch fails.

## `test_scripts/` — throwaway exploration

Local-only test / experiment / exploration scripts live at:

`C:\Users\likak\Desktop\ctk_maker\test_scripts\`

The folder is at the **repo root** (NOT under `tools/`) and is **gitignored** — anything saved there stays local and won't ship.

**What goes here:** ad-hoc Python scripts for visual experiments, widget probing, one-off renders, layout playgrounds — anything you'd otherwise scatter loose with `test_*.py` / `check_*.py` names.

**What does NOT go here:**
- pytest unit tests → `tests/` (separate folder, tracked, run by pytest)
- CI lints / pytest dependencies → `tools/`. Example: `tools/check_cross_platform.py` is a "check" script but is invoked by `tests/test_cross_platform_baseline.py` (pytest), so it stays in `tools/` (tracked). If a script is referenced from `tests/` or any tracked code, it must stay tracked.

## `.ctkproj` page scripting — build scripts

The recurring pattern for adding pages to a CTkMaker project programmatically (without the GUI).

### Locations

- **Target project:** `C:\Users\likak\Documents\CTkMaker\<ProjectName>\`
  - `project.json` — version 1, holds the `pages` list (each entry: `id` / `file` / `name`)
  - `assets/pages/<name>.ctkproj` — version 2 page files (one per page)
- **Clean widget library (variant source):** `C:\Users\likak\Documents\CTkMaker\Templates\assets\pages\<type>_clean.ctkproj` — one file per widget type, curated by the user. Files being unified to `_clean` suffix (`buttons_clean.ctkproj`, `labels_clean.ctkproj`, `selections_clean.ctkproj`); pre-rename names (`main.ctkproj` = buttons, `labels.ctkproj` = labels, `selections.ctkproj` = selections) may still appear mid-migration. The builder helper auto-scans all `*.ctkproj` in the pages dir; any widget whose name matches `^[a-z]+_\d+$` (e.g. `button_1`, `checkbox_3`) is treated as a template. Showcase widgets use descriptive names (`color_primary`, `h_sizes`) and are skipped automatically by the regex. If a required variant is missing from the clean library, ASK the user to add it — do not invent property names.
- **Showcases / projects:** `<type>_showcase.ctkproj` (e.g. `buttons_showcase.ctkproj`). Behavior lives in `CTkScript` classes in the project's top-level `scripts/` folder — attached in the builder, bindings stored inside the `.ctkproj` (script path + class + method). Renaming a `.ctkproj` no longer orphans anything (the old per-page `assets/scripts/` layout is gone).
- **Builder helper:** `C:\tmp\ctkproj_builder.py` — see API below. Loaded by every build script via `sys.path.insert(0, ...)`.
- **Build scripts:** `C:\tmp\build_<demo>.py` — one-shot generators, throwaway. Each script reads an EXISTING page file (user creates the empty page in CTkMaker GUI first) and replaces only its `widgets` + `name_counters`. **Never** write `project.json`; never create new pages programmatically.

### `ctkproj_builder.py` — shared API

Module state (loaded at import):

- **`TEMPLATES_DIR`** = `C:\Users\likak\Documents\CTkMaker\Templates\assets\pages`
- **`_TEMPLATE_NAME`** = `re.compile(r"^[a-z]+_\d+$")` — only widgets matching this pattern load as templates. Descriptive names (`color_primary`, `anim_pulse`) are filtered.
- **`_TEMPLATES`** — `dict[str, dict]`, name → widget node. Last-wins on key collision across pages.

Public API:

```python
new_id() -> str                                          # uuid4 string
list_templates() -> list[str]                            # sorted template names
clone(template_name, *, name, x, y, w, h,
      handlers=None, **prop_overrides) -> dict           # deep-copy + override
name_counters(widgets) -> dict[str, int]                 # auto-tally for ctkproj
make_toplevel_doc(*, name, w=600, h=400, widgets=None,
                  canvas_x=920, canvas_y=0,
                  window_overrides=None) -> dict         # full toplevel doc
update_page(page_path, *, document_index=0,
            widgets=None, window_size=None,
            append_documents=None) -> None               # I/O wrapper
```

`clone()` rules:
- Sets `id` (fresh uuid), `name`, `children=[]`, `handlers={}` if not supplied.
- Geometry overrides `x`, `y`, `width`, `height` always applied.
- Any `prop_overrides=None` is **skipped** (treat as "keep template default").
- Raises `RuntimeError` with the available template list if the requested `template_name` is missing — that's the trigger to ask the user to add a variant in the GUI.

`update_page()` mutates document at `document_index` (default 0): replaces `widgets` (and recomputes `name_counters`), resizes `width`/`height`, appends extra documents.

Build script skeleton:

```python
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from ctkproj_builder import clone, name_counters

PAGE_PATH = Path(r"C:\Users\likak\Documents\CTkMaker\Templates"
                 r"\assets\pages\<page>.ctkproj")

nodes: list[dict] = []
nodes.append(clone("button_1", name="my_btn", x=30, y=60, w=140, h=32,
                   text="Hi", fg_color="#22c55e"))

with PAGE_PATH.open("r", encoding="utf-8") as f:
    page = json.load(f)
doc = page["documents"][0]
doc["widgets"] = nodes
doc["name_counters"] = name_counters(nodes)
with PAGE_PATH.open("w", encoding="utf-8") as f:
    json.dump(page, f, indent=2, ensure_ascii=False)
```

## Exporter — widget naming

When CTkMaker exports a project (or runs F5 preview), each widget becomes an attribute on the window class. As of the 2026-05-01 fix, the exporter **uses the user-set `node.name` from the Properties panel** when it's a valid Python identifier, not a Python keyword, and not in `_RESERVED_VAR_NAMES`. Otherwise it falls back to `<type-lowercased>_<N>` (legacy default).

Source: `_resolve_var_names` in `app/io/code_exporter/__init__.py`.

A CTkTextbox the user named `content_textbox` IS emitted as `self.content_textbox`. A window-scoped CTkScript can write `self.window.content_textbox` directly.

**Reserved names (fixed since the 2026-05-01 gap):** `_RESERVED_VAR_NAMES` holds only the exporter's own emitted symbols (`_build_ui`) and is joined at validation time with `_ctk_inherited_names()` — every non-dunder attribute of `ctk.CTk` ∪ `ctk.CTkToplevel`. A widget named `title`, `geometry`, `mainloop`, `bind`, `configure`, `wm_*`, `winfo_*`, etc. is therefore rejected and falls back to `<type>_<N>` (reported via `_VAR_NAME_FALLBACKS`) instead of shadowing the inherited method. The old crash (CTkScrollableDropdown calling `root.title()` while a widget named `title` shadowed it) can no longer happen.

Handler signatures (per `app/widgets/event_registry.py`):
- Buttons / Switches / RadioButtons → `(self)`
- Slider / OptionMenu / ComboBox / SegmentedButton → `(self, value)`
- CTkEntry / CTkTextbox bind:* events → `(self, event=None)`

Handlers can't take widget refs via parameters — every widget access goes through `self.window.<user_name>`.

## Exporter — derived kwargs

CTkMaker-ის `code_exporter` constructor kwarg-ებს `node.properties`-დან აშენებs, `_NODE_ONLY_KEYS` / `_FONT_KEYS` ფილტრით — **`transform_properties()`-ს არ იძახებს** (მხოლოდ "mimics"; `code_exporter/__init__.py`-ის docstring-ის "matches transform_properties" შეცდომაში შემყვანია).

ამიტომ ნებისმიერი *derived / composite* kwarg — რომელიც raw property key **არ არის** — export-ში ცალკე უნდა გავიდეს:
- `state` (← `button_enabled`) — hardcoded special-case ბლოკი `code_exporter/__init__.py`-ში
- `text_color_hover` (← `text_hover` + `text_hover_color`) — `descriptor.export_kwarg_overrides()` → exporter-ის override fan-out loop emit-ავს

**How to apply:** ნებისმიერ Phase 2 editor batch-ზე (image tinting, font_autofit, ...) — თუ fork kwarg builder property key-ს 1:1 არ ემთხვევა, descriptor-ში `export_kwarg_overrides()` დაამატე, თორემ export-ში დაიკარგება. ხაფანგი: live workspace `transform_properties`-ით მუშაობს, ანუ live სწორი ჩანს და მხოლოდ **export** ტყდება ჩუმად — ამიტომ [[feedback_test_exports_yourself]] კრიტიკულია.

## Hand-written behavior — CTkScript

As of 1.50.x the old behavior-file model (a per-window `setup(window)` class under `assets/scripts/`, gated by `_doc_has_handlers`, plus the "attach one dummy handler" trick) is **removed**. Hand-written runtime logic now lives in **CTkScript** files:

- Subclass `CTkScript` in the project's top-level `scripts/` folder, then attach it to a widget or window in the builder.
- Widget-attached → `self.widget` (that widget only, no `self.window`). Window-attached → `self.window`, reaching widgets by builder name (`self.window.my_button`).
- Lifecycle hooks: `on_start` (after the UI builds) / `on_close` (window closing).
- Bind events to script methods in the Events panel; the exporter emits `self._script_N = ClassName()` and wires `command=self._script_N.<method>`. CTkMaker never edits the script file.

Base-class source of truth: `app/io/scripts/ctk_script.py`.

## Assets

**Lucide PNG icons** live at:

`C:\Users\likak\Desktop\lucide-icons\png-icons\`

When a new Lucide icon is needed:
1. User downloads/places PNG there (name matches the Lucide slug, e.g. `file-plus.png`)
2. Copy from that folder into `<project>/assets/icons/`
3. Icon loader (`app/ui/icons.py`) picks them up by bare name

Icon parameters per project policy: 16×16 px, stroke 2, color `#888888`, PNG RGBA.

## Competitor — CTkDesigner

**URL:** https://ctkdesigner.akascape.com/

**Author:** Akascape — same person who built `CTkScrollableDropdown` (the popup library vendored as inspiration for `app/widgets/scrollable_dropdown.py`).

**Why it matters:** Direct competitor in the same niche (CTk visual designers). The name `CTkDesigner` was originally considered for this project but was taken; final name picked = **CTkMaker** (PyPI verified free). Akascape's tooling is well-regarded in the CTk community — worth tracking for feature parity, UX inspiration, and differentiation. Don't suggest naming overlaps with Akascape's brand.
