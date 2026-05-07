from app.widgets.event_registry import (
    EVENT_REGISTRY,
    EventEntry,
    event_by_key,
    events_for,
    events_partitioned,
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


def test_event_entry_advanced_defaults_to_false():
    entry = EventEntry(
        "command", "on click", "click", "(self)", "command",
    )

    assert entry.advanced is False


def test_ctk_label_split_into_five_default_and_eleven_advanced():
    # CTkLabel is the first widget to use the advanced grouping —
    # five default events stay on the flat list and eleven sit in
    # the collapsible Advanced sub-section. Locking the split here
    # so a future registry edit can't silently re-shuffle the
    # default surface without an explicit test update.
    default, advanced = events_partitioned("CTkLabel")
    default_keys = {e.key for e in default}
    advanced_keys = {e.key for e in advanced}

    assert default_keys == {
        "bind:<Button-1>",
        "bind:<Double-Button-1>",
        "bind:<Enter>",
        "bind:<Leave>",
        "bind:<MouseWheel>",
    }
    assert advanced_keys == {
        "bind:<Button-2>",
        "bind:<Button-3>",
        "bind:<ButtonRelease-1>",
        "bind:<Motion>",
        "bind:<Configure>",
        "bind:<Map>",
        "bind:<Unmap>",
        "bind:<FocusIn>",
        "bind:<FocusOut>",
        "bind:<KeyPress>",
        "bind:<KeyRelease>",
    }


def test_events_partitioned_preserves_registration_order():
    default, advanced = events_partitioned("CTkLabel")
    full_order = [e.key for e in events_for("CTkLabel")]

    # Each partition keeps its entries in the order they appear
    # in EVENT_REGISTRY — callers rely on this for the cascade /
    # panel rendering to match the source file.
    assert [e.key for e in default] == [k for k in full_order if k in {e.key for e in default}]
    assert [e.key for e in advanced] == [k for k in full_order if k in {e.key for e in advanced}]


def test_events_partitioned_for_widget_without_advanced_events():
    default, advanced = events_partitioned("CTkButton")

    assert len(default) == 1
    assert advanced == []


def test_events_partitioned_unknown_widget_returns_two_empty_lists():
    default, advanced = events_partitioned("CompletelyMadeUpWidget")

    assert default == []
    assert advanced == []
