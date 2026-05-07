"""CircleLabel — CTkLabel override that supports full-corner-radius
labels with text, without the outer Frame growing past its configured
size.

Pure standalone Python — no CTkMaker dependency — so the exporter can
inline this module's source verbatim into generated ``.py`` files.

Why this exists
---------------
``customtkinter.CTkLabel._create_grid`` pads the inner ``tk.Label``
horizontally by ``min(corner_radius, current_height/2)``:

    self._label.grid(..., padx=min(corner_radius, current_height/2))

When ``2 * corner_radius >= width`` (typical full-circle / pill labels)
the left+right padx consume the entire label width and the text label
has no horizontal room — its natural width pushes the outer ``tk.Frame``
to grow, which silently breaks ``place``-layout neighbour spacing
(labels overlap each other on the canvas).

``CircleLabel`` zeroes ``corner_radius`` from the padx calculation
during ``_create_grid`` only. The canvas's actual rounded-shape draw
still uses the real ``corner_radius`` (read by ``_draw`` →
``DrawEngine``), so the visible rounded shape is unchanged — the layout
simply no longer reserves the rounded-corner area for padding.

Trade-off
---------
Very long text on a small label may visually extend into the
rounded-corner area. For typical short label text (1-3 chars, icons,
common badge labels) the text stays centered and there is no visible
bleed.
"""
import customtkinter as ctk


class CircleLabel(ctk.CTkLabel):
    """CTkLabel override — full-radius support without Frame growth."""

    def _create_grid(self):
        # Temporarily zero ``_corner_radius`` so the parent's ``padx``
        # computation (``min(corner_radius, height/2)``) collapses to
        # zero, leaving the label free to use the full inner width.
        # The canvas's actual draw path reads ``_corner_radius`` later
        # (from ``_draw``), so the visible rounded shape is unaffected.
        saved = self._corner_radius
        self._corner_radius = 0
        try:
            super()._create_grid()
        finally:
            self._corner_radius = saved
