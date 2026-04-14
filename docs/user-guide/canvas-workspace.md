# Canvas Workspace

> The center panel where you design your UI. Every widget on the canvas
> is a real CTk widget — what you see is what gets exported.

## Layout

The workspace has three stacked regions:

| Region | Purpose |
|---|---|
| Top tool bar | Select / Hand tool toggles |
| Canvas | Document rectangle with dot grid and your widgets |
| Status bar | Zoom controls and 100%-actual-size warning |

## Tools

| Tool | Shortcut | Action |
|---|---|---|
| Select | `V` | Click, drag, resize, nudge widgets |
| Hand | `H` | Pan the canvas without affecting the selection |

Press the tool button in the top bar or use the shortcut to switch.

## Placing widgets

Drag an entry from the **Widget Box** (left panel) and drop it on the
canvas. The drop point becomes the widget's `x` / `y`. Drop inside a
container (CTkFrame) to nest the widget as a child.

## Selecting

| Action | Shortcut |
|---|---|
| Select a widget | Click on it |
| Clear selection | Click empty canvas / `Escape` |

## Moving

| Action | Shortcut |
|---|---|
| Drag | Hold Left-click, move the mouse |
| Nudge 1 px | Arrow keys |
| Nudge 10 px | `Shift` + Arrow |

## Resizing

A selected widget shows eight handles (four corners + four edges).
Drag any handle to resize. Properties update live in the right panel.

## Deleting and renaming

| Action | Shortcut |
|---|---|
| Delete selected | `Delete` |
| Rename | Right-click → Rename |

Renaming only affects the builder-side name shown in the
[Object Tree](../widgets/README.md); the widget type and properties
are unchanged.

## Zoom and pan

| Action | Shortcut |
|---|---|
| Zoom in / out | `Ctrl +` / `Ctrl -` |
| Reset to 100% | `Ctrl 0` |
| Pan | Hand tool + drag |

Zoom levels: 25 %, 50 %, 75 %, 100 %, 125 %, 150 %, 200 %, 300 %, 400 %.
Fonts only render at their true size when zoom is 100 % — a yellow
warning appears in the status bar at any other level.

## Tips

- The **document rectangle** marks the target window bounds defined in
  your project settings. Widgets outside it won't appear in the export.
- The dot grid is purely visual; there is no snap-to-grid.
- Hand-tool dragging does not change selection; Select-tool drag on an
  empty canvas clears selection instead of panning.
