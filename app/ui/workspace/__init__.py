"""Workspace package — canvas surface + per-document chrome + widget
lifecycle wiring. The class used to live in a single 2 000-line
``workspace.py`` module; it's been split into focused submodules:

    ``core``             — the ``Workspace`` class itself (orchestrator).
    ``chrome``           — per-document title strip + drag / settings /
                           close buttons.
    ``controls``         — tool bar, pan state, status bar, keybindings.
    ``drag``             — widget drag-to-move / reparent interaction.
    ``layout_overlay``   — pack / grid manager kwargs + weight config.
    ``render``           — document rect + builder grid + visibility
                           mask.
    ``widget_lifecycle`` — widget add / remove / reparent / z-order /
                           visibility event handlers.

External callers still import ``from app.ui.workspace import
Workspace``; the re-export here keeps that path stable across the
refactor.
"""

from .core import Workspace

__all__ = ["Workspace"]
