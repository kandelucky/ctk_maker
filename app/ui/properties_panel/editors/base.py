"""Editor base class for the Properties panel.

An Editor encapsulates the per-row behavior for one schema property
type: overlay creation, value refresh, disabled styling, click routing.

All methods are no-ops by default — each concrete editor overrides
only the hooks it needs. The panel owns the overlay dicts and
project/commit access; editors receive the panel as their first
argument and read/write `panel._*_overlays` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..panel import PropertiesPanel


class Editor:
    """No-op base class. Override any method to customize behavior."""

    def populate(
        self,
        panel: "PropertiesPanel",
        iid: str,
        pname: str,
        prop: dict,
        value,
    ) -> None:
        """Attach any overlays for this row after the tree item exists."""

    def refresh(
        self,
        panel: "PropertiesPanel",
        iid: str,
        pname: str,
        prop: dict,
        value,
    ) -> None:
        """Update overlay appearance after a property value changed."""

    def set_disabled(
        self,
        panel: "PropertiesPanel",
        iid: str,
        pname: str,
        prop: dict,
        disabled: bool,
    ) -> None:
        """Sync overlay colors / cursors with the disabled_when state."""

    def on_single_click(
        self,
        panel: "PropertiesPanel",
        pname: str,
        prop: dict,
    ) -> bool:
        """Return True if the click was handled; False falls through."""
        return False

    def on_double_click(
        self,
        panel: "PropertiesPanel",
        pname: str,
        prop: dict,
        event,
    ) -> bool:
        """Return True if the double-click was handled."""
        return False
