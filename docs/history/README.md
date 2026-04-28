# Version history

Visual snapshots of CTkMaker across releases.

| Version | Screenshot | Highlights |
|---------|-----------|------------|
| **v1.0.6** | [![v1.0.6](v1.0.6.png)](v1.0.6.png) | In-app **Bug / Feature reporter** — Help menu + toolbar button open a structured form that submits via GitHub Issue Form template URL or markdown export. Plus a hotfix to v1.0.5's group selection (Ctrl+Click toggles whole group, orange bbox follows during drag). |
| **v1.0.3** | [![v1.0.3](v1.0.3.png)](v1.0.3.png) | **Alignment + distribution toolbar** — 6 align buttons (L/C/R + T/M/B) + 2 distribute (H/V). Auto-detects intent: 1 widget aligns to its container, multiple widgets align to each other. Single-undo per gesture. |
| **v1.0.1** | [![v1.0.1](v1.0.1.png)](v1.0.1.png) | **Card widget** with embedded image (anchor / tint / padding / preserve-aspect) plus a bug sweep across drop coords, hidden frames as drop targets, eye-icon cascade, and Save As asset copy. |
| **v0.0.14** | [![v0.0.14](v0.0.14.png)](v0.0.14.png) | **Grid place-based centring + workspace refactor.** CTkFrame's rounded-corner canvas broke tk's native `.grid()` math, so children now render via hand-computed `.place()` coords that handle every sticky combination. `WidgetLifecycle` extracted from workspace core. |
| **v0.0.9** | [![v0.0.9](v0.0.9.png)](v0.0.9.png) | **Multi-document canvas.** One `.ctkproj` holds a Main Window plus any number of Dialogs, all visible on the same canvas. Per-document chrome with drag, active highlight, palette drop targeting the doc under cursor, AddDialog preset picker. |
| **v0.0.8** | [![v0.0.8](v0.0.8.png)](v0.0.8.png) | **Phase 3 widgets + Undo / Redo.** 13 widgets land (Entry, CheckBox, ComboBox, OptionMenu, ProgressBar, RadioButton, SegmentedButton, Slider, Switch, Textbox, Tabview, ScrollableFrame, …). Full command-based history with the History panel (F9). |
| **v0.0.7** | [![v0.0.7](v0.0.7.png)](v0.0.7.png) | **Properties panel v2 rewrite** — ttk.Treeview backbone, flicker-free overlays, modular editor registry. |
| **v0.0.6** | [![v0.0.6](v0.0.6.png)](v0.0.6.png) | First widgets — CTkLabel / CTkFrame, workspace canvas, startup dialog. |
