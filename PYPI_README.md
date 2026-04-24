# CTkMaker

> **Visual UI designer for [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)** — drag and drop widgets, edit properties live, export as clean Python code.

🚧 **This is a placeholder release (v0.0.1) reserving the PyPI name.**
The full v1.0.0 release is under active development.

## What it is

A desktop visual designer for CustomTkinter. Drop widgets onto a canvas, edit their properties live, and export the result as runnable Python code.

- **Preview = Reality** — real CTk widgets rendered on the canvas, not a simulation
- **Multi-document canvas** — one project holds a Main Window plus any number of Dialogs
- **Layout managers** — `place` / `vbox` / `hbox` / `grid` with WYSIWYG rendering
- **Full undo / redo** — every mutation tracked
- **19+ widget descriptors** — buttons, labels, frames, entries, sliders, and more

## Installation (when v1.0.0 lands)

```bash
pip install ctkmaker
ctkmaker
```

## Current status

The source code lives at [github.com/kandelucky/ctk_maker](https://github.com/kandelucky/ctk_maker).
You can run the development version directly:

```bash
git clone https://github.com/kandelucky/ctk_maker.git
cd ctk_maker
pip install -r requirements.txt
python main.py
```

## License

MIT
