# Properties Panel

> The right-side editor for the currently selected widget.

## Overview

TODO: Schema-driven panel. The selected widget's descriptor declares a
property schema; the panel renders editors for each entry.
Source: [app/ui/properties_panel.py](../../app/ui/properties_panel.py).

## Editor types

TODO: Table of supported editor types (string, int, float, color, font,
enum, bool, image) and how they map to schema field types.

## Color editor

TODO: How the tint color picker is invoked.
Library: [ctk-tint-color-picker](https://pypi.org/project/ctk-tint-color-picker/).

## Multi-selection behavior

TODO: What happens when multiple widgets are selected — common properties only?

## Live preview

TODO: How edits propagate to the canvas in real time via the event bus.
Link: [Event Bus](../architecture/event-bus.md).

## Reset & defaults

TODO: Reset-to-default behavior per property.
