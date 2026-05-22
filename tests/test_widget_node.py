from app.core.widget_node import WidgetNode


def _sc(cls, method, scope="widget"):
    return {
        "kind": "script_call", "class": cls,
        "method": method, "scope": scope,
    }


def _populated_node():
    node = WidgetNode("CTkButton", {"text": "Hi", "fg_color": "#abc"})
    node.name = "ok_button"
    node.visible = False
    node.locked = True
    node.parent_slot = "Tab 1"
    node.group_id = "grp-1"
    node.description = "Submits the login form."
    node.handlers = {
        "command": [_sc("Form", "submit", "window"), _sc("Log", "click")],
        "bind:<Enter>": [_sc("Hover", "on_enter")],
    }
    child = WidgetNode("CTkLabel", {"text": "child"})
    child.parent = node
    node.children.append(child)
    return node


def test_to_dict_from_dict_full_round_trip():
    original = _populated_node()

    restored = WidgetNode.from_dict(original.to_dict())

    assert restored.id == original.id
    assert restored.name == original.name
    assert restored.widget_type == original.widget_type
    assert restored.properties == original.properties
    assert restored.visible is False
    assert restored.locked is True
    assert restored.parent_slot == "Tab 1"
    assert restored.group_id == "grp-1"
    assert restored.description == "Submits the login form."
    assert restored.handlers == original.handlers
    assert len(restored.children) == 1
    assert restored.children[0].widget_type == "CTkLabel"
    assert restored.children[0].parent is restored


def test_to_dict_drops_empty_handlers():
    node = WidgetNode("CTkButton")

    assert "handlers" not in node.to_dict()


def test_to_dict_drops_empty_handler_lists():
    node = WidgetNode("CTkButton")
    node.handlers = {"command": [], "bind:<Enter>": [_sc("H", "go")]}

    assert node.to_dict()["handlers"] == {"bind:<Enter>": [_sc("H", "go")]}


def test_from_dict_keeps_script_call_entries():
    data = {
        "id": "abc",
        "widget_type": "CTkButton",
        "properties": {},
        "handlers": {"command": [_sc("Counter", "bump", "widget")]},
    }

    node = WidgetNode.from_dict(data)

    assert node.handlers == {"command": [_sc("Counter", "bump", "widget")]}
    # Round-trips unchanged.
    assert WidgetNode.from_dict(node.to_dict()).handlers == node.handlers


def test_from_dict_drops_legacy_handler_entries():
    # Clean break: page-method strings, ref_call and library_call are
    # dropped on load — only script_call survives.
    data = {
        "id": "abc",
        "widget_type": "CTkButton",
        "properties": {},
        "handlers": {
            "command": [
                "legacy_method",
                "",
                {"kind": "ref_call", "ref": "r", "method": "m", "args": []},
                {"kind": "library_call", "script": "h.py", "method": "f"},
                _sc("Counter", "bump"),
            ],
        },
    }

    node = WidgetNode.from_dict(data)

    assert node.handlers == {"command": [_sc("Counter", "bump")]}


def test_from_dict_drops_event_with_only_legacy_entries():
    data = {
        "id": "abc",
        "widget_type": "CTkButton",
        "properties": {},
        "handlers": {"command": ["legacy_method"]},
    }

    node = WidgetNode.from_dict(data)

    assert node.handlers == {}


def test_from_dict_renames_legacy_widget_types():
    data = {
        "id": "abc",
        "widget_type": "Shape",
        "properties": {},
    }

    node = WidgetNode.from_dict(data)

    assert node.widget_type == "Card"


def test_to_dict_properties_is_independent_copy():
    node = WidgetNode("CTkButton", {"text": "Hi"})

    data = node.to_dict()
    data["properties"]["text"] = "Mutated"

    assert node.properties["text"] == "Hi"
