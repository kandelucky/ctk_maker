# Code Generation

> How the tree of `WidgetNode` objects becomes a standalone Python file.

## Goals

TODO: Produce code that is (1) runnable as-is, (2) readable, (3) close to
what a human would write by hand.

## Exporter entry point

TODO: Document the main function in [app/io/code_exporter.py](../../app/io/code_exporter.py).

## Pipeline

```
WidgetNode tree
    │
    ▼
 descriptor.transform_properties(node.properties)
    │
    ▼
 constructor kwargs
    │
    ▼
 emitted source lines
    │
    ▼
 final .py file
```

TODO: Describe each stage.

## `transform_properties`

TODO: Every descriptor owns a `transform_properties` method that maps
schema properties (as stored in the project file) to real CTk constructor
kwargs. This is the single place where export and live-render diverge
in their handling of a property.

## Output template

TODO: Show the import block, class skeleton, and placement calls that
wrap the emitted widgets.

## Limitations

TODO: Event handlers, custom code, non-`place` layout managers.
