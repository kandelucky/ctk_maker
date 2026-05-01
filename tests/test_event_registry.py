from app.widgets.event_registry import (
    EVENT_REGISTRY,
    EventEntry,
    event_by_key,
    events_for,
)


def test_events_for_button_has_single_command_entry():
    entries = events_for("CTkButton")

    assert len(entries) == 1
    entry = entries[0]
    assert entry.key == "command"
    assert entry.wiring_kind == "command"
    assert entry.signature == "(self)"
    assert entry.verb == "click"


def test_events_for_unknown_widget_returns_empty_list():
    assert events_for("CTkLabel") == []
    assert events_for("CompletelyMadeUpWidget") == []


def test_events_for_slider_passes_value_in_signature():
    entries = events_for("CTkSlider")

    assert len(entries) == 1
    assert entries[0].signature == "(self, value)"
    assert entries[0].wiring_kind == "command"


def test_events_for_entry_has_bind_wirings():
    entries = events_for("CTkEntry")
    keys = [e.key for e in entries]

    assert "bind:<Return>" in keys
    assert "bind:<KeyRelease>" in keys
    assert all(e.wiring_kind == "bind" for e in entries)
    assert all(e.signature == "(self, event=None)" for e in entries)


def test_event_by_key_returns_matching_entry():
    entry = event_by_key("CTkButton", "command")

    assert isinstance(entry, EventEntry)
    assert entry.verb == "click"


def test_event_by_key_returns_none_for_missing_key():
    assert event_by_key("CTkButton", "bogus") is None
    assert event_by_key("CTkLabel", "command") is None
    assert event_by_key("UnknownWidget", "command") is None


def test_event_by_key_resolves_bind_style_event():
    entry = event_by_key("CTkEntry", "bind:<Return>")

    assert entry is not None
    assert entry.wiring_kind == "bind"
    assert entry.verb == "return_pressed"


def test_event_keys_are_unique_within_each_widget():
    for widget_type, entries in EVENT_REGISTRY.items():
        keys = [e.key for e in entries]
        assert len(keys) == len(set(keys)), (
            f"duplicate event key in {widget_type}: {keys}"
        )
