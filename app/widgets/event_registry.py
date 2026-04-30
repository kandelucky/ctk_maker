"""Phase 2 — widget → event catalog.

Drives the right-click "Add handler ▸" cascade and (in Part 4) the
Properties panel "Handlers" group. Each ``EventEntry`` pairs:

- ``key`` — storage key in ``WidgetNode.handlers``. ``"command"`` for
  click-style callbacks; ``"bind:<seq>"`` for tk-bind events.
- ``label`` — human-readable name shown in the menu cascade.
- ``verb`` — snake_case suffix for the auto-generated method name
  (``on_<widget>_<verb>``).
- ``signature`` — parameter list that lands on the stub. Buttons /
  Switches / RadioButtons take ``(self)``; CTkSlider / ComboBox /
  OptionMenu / SegmentedButton take ``(self, value)`` because CTk
  passes the new value to the command callback. Bind-style events
  take ``(self, event=None)``.
- ``wiring_kind`` — ``"command"`` (constructor kwarg) vs ``"bind"``
  (post-construction ``widget.bind(seq, fn)`` call). Read by Part 3's
  exporter + runtime wiring.

Adding a new widget's events: extend ``EVENT_REGISTRY`` here and the
matching wiring in (Part 3) ``app/widgets/event_wirings.py``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventEntry:
    key: str
    label: str
    verb: str
    signature: str
    wiring_kind: str


_COMMAND = "command"
_BIND = "bind"

EVENT_REGISTRY: dict[str, list[EventEntry]] = {
    "CTkButton": [
        EventEntry("command", "on click", "click", "(self)", _COMMAND),
    ],
    "CTkSwitch": [
        EventEntry("command", "on toggle", "toggle", "(self)", _COMMAND),
    ],
    "CTkCheckBox": [
        EventEntry("command", "on toggle", "toggle", "(self)", _COMMAND),
    ],
    "CTkRadioButton": [
        EventEntry("command", "on select", "select", "(self)", _COMMAND),
    ],
    "CTkSlider": [
        EventEntry(
            "command", "on change", "change",
            "(self, value)", _COMMAND,
        ),
    ],
    "CTkSegmentedButton": [
        EventEntry(
            "command", "on select", "select",
            "(self, value)", _COMMAND,
        ),
    ],
    "CTkComboBox": [
        EventEntry(
            "command", "on select", "select",
            "(self, value)", _COMMAND,
        ),
    ],
    "CTkOptionMenu": [
        EventEntry(
            "command", "on select", "select",
            "(self, value)", _COMMAND,
        ),
    ],
    "CTkEntry": [
        EventEntry(
            "bind:<Return>", "on Return", "return_pressed",
            "(self, event=None)", _BIND,
        ),
        EventEntry(
            "bind:<KeyRelease>", "on key release", "key_release",
            "(self, event=None)", _BIND,
        ),
        EventEntry(
            "bind:<FocusOut>", "on focus out", "focus_out",
            "(self, event=None)", _BIND,
        ),
    ],
    "CTkTextbox": [
        EventEntry(
            "bind:<KeyRelease>", "on key release", "key_release",
            "(self, event=None)", _BIND,
        ),
        EventEntry(
            "bind:<FocusOut>", "on focus out", "focus_out",
            "(self, event=None)", _BIND,
        ),
    ],
}


def events_for(widget_type: str) -> list[EventEntry]:
    """Events available on ``widget_type``. Empty list when the type
    has no registered events (Label, Frame, Image, etc.) — callers
    use this to decide whether to render the cascade at all.
    """
    return EVENT_REGISTRY.get(widget_type, [])


def event_by_key(widget_type: str, key: str) -> EventEntry | None:
    """Look up a single ``EventEntry`` by its storage key. Used by
    the exporter / runtime wiring when re-resolving a binding read
    from a saved project.
    """
    for entry in events_for(widget_type):
        if entry.key == key:
            return entry
    return None
