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
- ``advanced`` — when True, the entry renders inside a collapsible
  "Advanced" sub-section instead of the flat default list. Used to
  shorten the surface for widgets with many bind events (CTkLabel)
  by hiding rare / high-frequency / takefocus-gated events behind
  one extra click. Default False.
- ``description`` — one-line plain-English explanation of when the
  event fires + what gets passed to the handler. Surfaced in the
  Properties panel hover tooltip on event-header rows. Default
  empty falls back to the capitalised ``label``.

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
    # Free-form caveat shown alongside the event in cascades / docs —
    # e.g. "fires at 60+ Hz" or "requires takefocus=True". Empty for
    # events that have no special precondition or perf concern.
    warning: str = ""
    # When True, the event renders inside an "Advanced" sub-section
    # (collapsible group in the Properties panel + nested submenu in
    # the right-click cascade) instead of the flat default list.
    # Reserved for events that are rarely needed, fire at high
    # frequency, or carry a precondition the average user would not
    # expect — keeps the default surface short while leaving the
    # full registry one click away.
    advanced: bool = False
    # One-line "what does this event do" — shown in the Properties
    # panel hover tooltip on event-header rows. Empty falls back to
    # the capitalised label so older entries still render something.
    description: str = ""


_COMMAND = "command"
_BIND = "bind"

EVENT_REGISTRY: dict[str, list[EventEntry]] = {
    "CTkButton": [
        EventEntry(
            "command", "on click", "click", "(self)", _COMMAND,
            description="Fires when the user clicks the button.",
        ),
    ],
    "CTkLabel": [
        # CTkLabel has no `command` constructor kwarg — every binding
        # is post-construction `.bind()`, which CTkLabel routes onto
        # both the inner canvas and inner Tk Label so the hit-area
        # covers the rounded corners as well as the text glyphs.
        # ----- Mouse buttons -----
        EventEntry(
            "bind:<Button-1>", "on click", "click",
            "(self, event=None)", _BIND,
            description=(
                "Fires on left mouse button click anywhere on the "
                "label's body."
            ),
        ),
        EventEntry(
            "bind:<Double-Button-1>", "on double click", "double_click",
            "(self, event=None)", _BIND,
            description="Fires when the user double-clicks the label.",
        ),
        EventEntry(
            "bind:<Button-2>", "on middle click", "middle_click",
            "(self, event=None)", _BIND, advanced=True,
            description="Fires on middle mouse button click.",
        ),
        EventEntry(
            "bind:<Button-3>", "on right click", "right_click",
            "(self, event=None)", _BIND, advanced=True,
            description=(
                "Fires on right mouse button click — typical place "
                "to open a context menu."
            ),
        ),
        EventEntry(
            "bind:<ButtonRelease-1>", "on mouse release", "mouse_release",
            "(self, event=None)", _BIND, advanced=True,
            description=(
                "Fires when the user releases the left mouse button "
                "after pressing it."
            ),
        ),
        # ----- Mouse motion / wheel -----
        EventEntry(
            "bind:<Enter>", "on mouse enter", "mouse_enter",
            "(self, event=None)", _BIND,
            description="Fires when the cursor enters the label's bounds.",
        ),
        EventEntry(
            "bind:<Leave>", "on mouse leave", "mouse_leave",
            "(self, event=None)", _BIND,
            description="Fires when the cursor leaves the label's bounds.",
        ),
        EventEntry(
            "bind:<Motion>", "on mouse move", "mouse_move",
            "(self, event=None)", _BIND,
            warning="Fires at 60+ Hz while the cursor is inside — "
                    "keep the handler cheap.",
            advanced=True,
            description=(
                "Fires while the cursor moves across the label. "
                "event.x / event.y carry the cursor position."
            ),
        ),
        EventEntry(
            "bind:<MouseWheel>", "on mouse wheel", "mouse_wheel",
            "(self, event=None)", _BIND,
            description=(
                "Fires when the user scrolls the mouse wheel over the "
                "label. Direction is in event.delta."
            ),
        ),
        # ----- Lifecycle / geometry -----
        EventEntry(
            "bind:<Configure>", "on resize", "resize",
            "(self, event=None)", _BIND,
            warning="Fires repeatedly during a window resize — "
                    "keep the handler cheap.",
            advanced=True,
            description=(
                "Fires when the label's geometry (size or position) "
                "changes."
            ),
        ),
        EventEntry(
            "bind:<Map>", "on shown", "shown",
            "(self, event=None)", _BIND, advanced=True,
            description=(
                "Fires when the label becomes visible (mapped onto "
                "the screen)."
            ),
        ),
        EventEntry(
            "bind:<Unmap>", "on hidden", "hidden",
            "(self, event=None)", _BIND, advanced=True,
            description=(
                "Fires when the label becomes hidden (unmapped from "
                "the screen)."
            ),
        ),
        # ----- Focus / keyboard (require takefocus=True) -----
        EventEntry(
            "bind:<FocusIn>", "on focus in", "focus_in",
            "(self, event=None)", _BIND,
            warning="Requires takefocus=True; the Label cannot "
                    "receive focus otherwise.",
            advanced=True,
            description="Fires when the label receives keyboard focus.",
        ),
        EventEntry(
            "bind:<FocusOut>", "on focus out", "focus_out",
            "(self, event=None)", _BIND,
            warning="Requires takefocus=True; the Label cannot "
                    "receive focus otherwise.",
            advanced=True,
            description="Fires when the label loses keyboard focus.",
        ),
        EventEntry(
            "bind:<KeyPress>", "on key press", "key_press",
            "(self, event=None)", _BIND,
            warning="Requires takefocus=True; key events are "
                    "delivered only to the focused widget.",
            advanced=True,
            description=(
                "Fires while a key is held down on the focused label. "
                "event.keysym names the key."
            ),
        ),
        EventEntry(
            "bind:<KeyRelease>", "on key release", "key_release",
            "(self, event=None)", _BIND,
            warning="Requires takefocus=True; key events are "
                    "delivered only to the focused widget.",
            advanced=True,
            description=(
                "Fires when a key is released on the focused label."
            ),
        ),
    ],
    "CTkSwitch": [
        EventEntry(
            "command", "on toggle", "toggle", "(self)", _COMMAND,
            description="Fires when the user flips the switch on or off.",
        ),
    ],
    "CTkCheckBox": [
        EventEntry(
            "command", "on toggle", "toggle", "(self)", _COMMAND,
            description=(
                "Fires when the user toggles the checkbox on or off."
            ),
        ),
    ],
    "CTkRadioButton": [
        EventEntry(
            "command", "on select", "select", "(self)", _COMMAND,
            description=(
                "Fires when the user picks this radio button — group "
                "siblings deselect automatically."
            ),
        ),
    ],
    "CTkSlider": [
        EventEntry(
            "command", "on change", "change",
            "(self, value)", _COMMAND,
            description=(
                "Fires every time the slider's value changes; the new "
                "value is passed as the second argument."
            ),
        ),
    ],
    "CTkSegmentedButton": [
        EventEntry(
            "command", "on select", "select",
            "(self, value)", _COMMAND,
            description=(
                "Fires when the user picks a segment; the picked "
                "segment's text is passed as the second argument."
            ),
        ),
    ],
    "CTkComboBox": [
        EventEntry(
            "command", "on select", "select",
            "(self, value)", _COMMAND,
            description=(
                "Fires when the user picks a value from the dropdown "
                "or commits a typed value; the value is passed as the "
                "second argument."
            ),
        ),
    ],
    "CTkOptionMenu": [
        EventEntry(
            "command", "on select", "select",
            "(self, value)", _COMMAND,
            description=(
                "Fires when the user picks a value from the dropdown; "
                "the value is passed as the second argument."
            ),
        ),
    ],
    "CTkEntry": [
        EventEntry(
            "bind:<Return>", "on Return", "return_pressed",
            "(self, event=None)", _BIND,
            description=(
                "Fires when the user presses Enter while the entry "
                "has focus."
            ),
        ),
        EventEntry(
            "bind:<KeyRelease>", "on key release", "key_release",
            "(self, event=None)", _BIND,
            description=(
                "Fires every time a key is released — useful for live "
                "validation or filtering as the user types."
            ),
        ),
        EventEntry(
            "bind:<FocusOut>", "on focus out", "focus_out",
            "(self, event=None)", _BIND,
            description=(
                "Fires when the entry loses focus — typical place to "
                "commit a final value."
            ),
        ),
    ],
    "CTkTextbox": [
        EventEntry(
            "bind:<KeyRelease>", "on key release", "key_release",
            "(self, event=None)", _BIND,
            description=(
                "Fires every time a key is released — useful for live "
                "counts or validation while the user types."
            ),
        ),
        EventEntry(
            "bind:<FocusOut>", "on focus out", "focus_out",
            "(self, event=None)", _BIND,
            description="Fires when the textbox loses focus.",
        ),
    ],
}


def events_for(widget_type: str) -> list[EventEntry]:
    """Events available on ``widget_type``. Empty list when the type
    has no registered events (Frame, Image, etc.) — callers use this
    to decide whether to render the cascade at all.
    """
    return EVENT_REGISTRY.get(widget_type, [])


def events_partitioned(
    widget_type: str,
) -> tuple[list[EventEntry], list[EventEntry]]:
    """Split ``events_for(widget_type)`` into ``(default, advanced)``
    in registration order. Callers that render the cascade / Properties
    panel use this to draw the flat default block + the collapsible
    "Advanced" sub-section without re-implementing the partition.
    """
    default_entries: list[EventEntry] = []
    advanced_entries: list[EventEntry] = []
    for entry in events_for(widget_type):
        (advanced_entries if entry.advanced else default_entries).append(entry)
    return default_entries, advanced_entries


def event_by_key(widget_type: str, key: str) -> EventEntry | None:
    """Look up a single ``EventEntry`` by its storage key. Used by
    the exporter / runtime wiring when re-resolving a binding read
    from a saved project.
    """
    for entry in events_for(widget_type):
        if entry.key == key:
            return entry
    return None
