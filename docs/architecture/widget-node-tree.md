# Widget Node Tree

> The in-memory representation of the user's design.

## What it is

TODO: The canvas is backed by a tree of `WidgetNode` objects — one per
placed widget. The tree is the source of truth; rendered CTk widgets are
mirrors of it. Source: [app/core/widget_node.py](../../app/core/widget_node.py).

## Node shape

TODO: Fields per node — `id`, `type`, `properties`, `children`, `parent`,
position, size.

## Tree operations

TODO: Add, remove, reparent, reorder, find-by-id, traverse.

## Serialization

TODO: How a node serializes to JSON (and how the tree is rehydrated on load).
Link to [Saving & Loading](../user-guide/saving-loading.md).

## Rendering

TODO: How each node gets paired with a real CTk widget on the canvas.

## Invariants

TODO: Every node has a unique id; root nodes have `parent = None`; etc.
