# CTkMaker

Drag-and-drop visual designer for **[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)** — design Python GUIs without writing layout code by hand.

> **v1.2.0** — **Local variables** (per-window) alongside the existing project-wide globals; cross-document widgets auto-migrate their bindings on reparent / paste. Code export routes globals onto the main window; Toplevels read them via `self.master.var_*`. **Prefab library** — save any selection as a reusable `.ctkprefab` and drag it back onto the canvas from the Palette's new Prefabs tab.
>
> ⚠️ **Tested on Windows only.** macOS and Linux are not verified for this release — feedback and contributions welcome.

[![CTkMaker canvas](docs/screenshots/canvas.png)](docs/screenshots/canvas.png)

## Project structure

A CTkMaker project is organised in four levels:

- **Project** — a folder containing one or more page files plus a shared asset pool
- **Page** — a single `.ctkproj` design (Login, Dashboard, Settings, ...) — pages share the project's fonts / images / icons
- **Window** — a Tk window inside a page; either the **Main Window** (one per page) or a **Dialog Window** (zero or more)
- **Widget** — buttons, labels, frames, etc. nested inside a window

## What it does

- **Visual canvas** — real CTk widgets on a zoomable workspace. What you see is what you get. Multiple windows (main + dialogs) live on the same canvas in one page.
- **Widgets — 20 in the palette:** Button, Segmented Button, Label, Image, Card, Progress Bar, Check Box, Radio Button, Switch, Entry, Textbox, Combo Box, Option Menu, Slider, Frame, Scrollable Frame, Tab View, Vertical Layout, Horizontal Layout, Grid Layout. Richer property editing than raw CTk: drag-scrub numbers, paired font family + size, multiline overlays, segmented value editor, scrollable dropdown for ComboBox / OptionMenu, color swatches with eyedropper. Open **Tools → Inspect CTk Widget** to see every property side-by-side — native CTk parameters vs builder-added helpers.
- **Variables + property bindings (two-level)** — declare shared values (string / int / float / bool) once and bind them to widget properties from the Properties panel with a single click on the row's diamond icon. **Global** variables (blue) live on the project; **Local** variables (orange) live on a single window and stay invisible to widgets in other windows. Reparent or paste a widget into another window and its local bindings are auto-migrated with a status toast. Updates propagate live across every bound widget on the canvas — typing into one Entry mirrors instantly into every Label / Switch / Slider sharing the variable. Exported code routes globals onto the main window (`self.var_X`); Toplevels read them via `self.master.var_X`, and locals attach to their owning class.
- **Prefab library** — save any selection on the canvas as a reusable prefab (`.ctkprefab` zip), organise prefabs into folders inside the Palette's Prefabs tab, then drag back onto any canvas to instantiate with fresh UUIDs. Real-time search filter, single-widget prefabs show their type icon, multi-widget fragments fall back to a generic icon. Lives in your user-wide `%APPDATA%/CTkMaker/prefabs/` folder so prefabs follow you across projects. Variable bindings inside a prefab are stripped to literals on save — the prefab stays self-contained when dropped into a project that doesn't share those variables.
- **Widget descriptions (AI bridge)** — every widget has a free-form description field for plain-language intent ("when clicked, add the digit 1 to the display"). Export optionally emits descriptions as Python comments above each widget — paste the file into your favourite AI to have it fill in the missing logic.
- **Layout managers** — `place`, `vbox`, `hbox`, `grid` rendered with the actual Tk pack/grid managers. Drop into cells, drag to reparent, even across windows.
- **Alignment & distribution** — toolbar buttons to align widgets (Left / Center / Right + Top / Middle / Bottom) and distribute them evenly. Auto-detects intent: a single widget aligns to its container, multiple widgets align to each other.
- **Marquee selection + smart snap guides** — drag a rectangle on empty canvas to multi-select; while dragging a widget, cyan guide lines snap its edges / centre to siblings and to the container. Hold Alt to bypass.
- **Groups** — Ctrl+G binds a same-parent selection together; clicking any member targets the whole group, fast follow-up drills to a single member, drag always carries the group as one. Object Tree shows them as a virtual `◆ Group (n)` parent with members nested in soft orange. Ctrl+Shift+G dissolves the group.
- **Asset system** — fonts, images, and 1700+ Lucide icons managed inside the project folder. Tinted PNGs, system-font auto-import, portable references.
- **Live preview** — run any window as a real CTk app in one click; floating **Screenshot · F12** button saves the client area as PNG to share.
- **Clean code export** — one runnable Python file per window. Optional `.zip` bundle (Python code + assets) for sharing. Per-page export ships only the assets that page actually references.

## Screenshots

[![Startup screen](docs/screenshots/startup.png)](docs/screenshots/startup.png)

*Startup — recent projects on the left, new-project form on the right with device + screen-size presets.*

## Quick start

```bash
git clone https://github.com/kandelucky/ctk_maker.git
cd ctk_maker
pip install -r requirements.txt
python main.py
```

## Documentation

Full docs live in the [Wiki](https://github.com/kandelucky/ctk_maker/wiki):

- [User Guide](https://github.com/kandelucky/ctk_maker/wiki/User-Guide) — workflow walkthrough
- [Widgets](https://github.com/kandelucky/ctk_maker/wiki/Widgets) — every supported widget + properties
- [Keyboard Shortcuts](https://github.com/kandelucky/ctk_maker/wiki/Keyboard-Shortcuts) — full reference
- [Version history](docs/history/) — screenshots and notes from each release

## Reporting issues

Found a bug or have an idea? Use **Help → Report a Bug** (or the toolbar button on the right) — a guided form opens that submits straight to the GitHub issue tracker, or saves a markdown file you can email instead. You can also [open an issue directly](https://github.com/kandelucky/ctk_maker/issues).

## Tech stack

- **Python 3.12+** (tested on 3.14)
- **CustomTkinter** 5.2.2+
- **Pillow**, **tkextrafont**, **ctk-tint-color-picker**

## What's next

- Event handlers — right-click a widget → "On Click" stubs a method in a companion behavior file, ready for the user to fill in
- Visual scripting — node editor for wiring widgets together without writing Python
- Custom user widgets + plugin system
- Distribution: PyInstaller bundles, installers, auto-updater

## Support

If CTkMaker helps you, [buy me a coffee ☕](https://buymeacoffee.com/Kandelucky_dev).

## License

MIT
