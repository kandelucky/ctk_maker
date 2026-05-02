"""CircleButton — CTkButton override that supports full-corner-radius
buttons with text, without the outer Frame growing past its configured
size.

Pure standalone Python — no CTkMaker dependency — so the exporter can
inline this module's source verbatim into generated ``.py`` files.

Why this exists
---------------
``customtkinter.CTkButton._create_grid`` reserves
``corner_radius`` worth of space on each outer column so the
rounded-corner area never collides with text or icon labels:

    scaled_minsize_columns = max(corner_radius, border_width + 1,
                                 border_spacing) * widget_scaling

When ``2 * corner_radius >= width`` (typical for full-circle / pill
buttons) those reservations consume the entire button width and the
text label has no horizontal room — its natural width pushes the outer
``tk.Frame`` to grow, which silently breaks ``place``-layout neighbour
spacing (buttons overlap each other on the canvas).

``CircleButton`` strips ``corner_radius`` from the column-minsize calc
during ``_create_grid`` only. The canvas's actual rounded-shape draw
still uses the real ``corner_radius`` (set elsewhere via
``_draw`` → ``DrawEngine``), so the visual rounded shape is unchanged
— the layout simply no longer treats the rounded-corner area as
off-limits for content.

Trade-off
---------
Very long text on a small button may visually extend into the
rounded-corner area. For typical short button text (1-3 chars, icons,
common action labels) the text stays centered and there is no visible
bleed.
"""
import customtkinter as ctk


class CircleButton(ctk.CTkButton):
    """CTkButton override — full-radius support without Frame growth."""

    def _create_grid(self):
        # Temporarily lie about ``_corner_radius`` so the parent's
        # outer-column ``minsize`` computation reserves only the border
        # space, not the rounded-corner area. The canvas's actual draw
        # path reads ``_corner_radius`` later (from ``_draw``), so the
        # visible rounded shape is unaffected.
        saved = self._corner_radius
        self._corner_radius = max(self._border_width + 1, self._border_spacing)
        try:
            super()._create_grid()
        finally:
            self._corner_radius = saved
