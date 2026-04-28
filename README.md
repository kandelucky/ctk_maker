# CTkMaker

Drag-and-drop visual designer for **[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)** — design Python GUIs without writing layout code by hand.

> **v1.1.0** — **Group hide/lock**: virtual `◆ Group` row in Object Tree gets eye + lock cells that batch-toggle every member as one undo step. **Group-aware alignment + distribution**: a fully-selected group counts as one block (combined bbox), so it moves as a unit against another widget instead of having its members align to each other first. **Preview screenshot**: every preview window now has a floating "⬜ Screenshot · F12" button that saves the client area as PNG — handy for sharing in-progress designs with a client. Plus About + bug-reporter polish (Discussions link, wiki intro banner).
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
- **Layout managers** — `place`, `vbox`, `hbox`, `grid` rendered with the actual Tk pack/grid managers. Drop into cells, drag to reparent, even across windows.
- **Alignment & distribution** — toolbar buttons to align widgets (Left / Center / Right + Top / Middle / Bottom) and distribute them evenly. Auto-detects intent: a single widget aligns to its container, multiple widgets align to each other.
- **Marquee selection + smart snap guides** — drag a rectangle on empty canvas to multi-select; while dragging a widget, cyan guide lines snap its edges / centre to siblings and to the container. Hold Alt to bypass.
- **Groups** — Ctrl+G binds a same-parent selection together; clicking any member targets the whole group, fast follow-up drills to a single member, drag always carries the group as one. Object Tree shows them as a virtual `◆ Group (n)` parent with members nested in soft orange. Ctrl+Shift+G dissolves the group.
- **Asset system** — fonts, images, and 1700+ Lucide icons managed inside the project folder. Tinted PNGs, system-font auto-import, portable references.
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

- Variables panel + event handlers
- Custom user widgets + plugin system
- Distribution: PyInstaller bundles, installers, auto-updater

## Support

If CTkMaker helps you, [buy me a coffee ☕](https://buymeacoffee.com/Kandelucky_dev).

## License

MIT
