# Exporting Code

> Generate clean, runnable Python from your design.

## Overview

TODO: What the exporter produces — a standalone `.py` file that imports
`customtkinter` and reconstructs the designed UI.
Source: [app/io/code_exporter.py](../../app/io/code_exporter.py).

## Export flow

TODO: File → Export → choose path → done.

## Output structure

TODO: Show a minimal before/after — a canvas with one button, and the
generated Python for it.

```python
# TODO: example
```

## Property → constructor mapping

TODO: Reference how each descriptor's `transform_properties` maps schema
properties to the CTk constructor kwargs.
Link: [Code Generation](../architecture/code-generation.md).

## Limitations

TODO: What is **not** exported (event handlers, custom code, layout managers
beyond `place`, etc.).

## Post-export tips

TODO: How to wire up callbacks after export.
