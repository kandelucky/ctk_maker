from app.core.variables import (
    COLOR_DEFAULT,
    VAR_TYPES,
    VariableEntry,
    coerce_default_for_type,
    compatible_var_types,
    is_valid_hex,
)


def test_color_in_var_types():
    assert "color" in VAR_TYPES


def test_color_round_trip_through_to_from_dict():
    entry = VariableEntry(name="accent", type="color", default="#abcdef")
    restored = VariableEntry.from_dict(entry.to_dict())
    assert restored.type == "color"
    assert restored.default == "#abcdef"
    assert restored.name == "accent"
    assert restored.id == entry.id


def test_color_short_hex_round_trip():
    entry = VariableEntry(name="x", type="color", default="#abc")
    data = entry.to_dict()
    assert data["type"] == "color"
    assert data["default"] == "#abc"
    restored = VariableEntry.from_dict(data)
    assert restored.type == "color"
    assert restored.default == "#abc"


def test_unknown_type_falls_back_to_str():
    restored = VariableEntry.from_dict({"type": "rainbow", "default": "x"})
    assert restored.type == "str"


def test_coerce_default_for_color_accepts_valid_hex():
    assert coerce_default_for_type("#abcdef", "color") == "#abcdef"
    assert coerce_default_for_type("#ABC", "color") == "#ABC"
    assert coerce_default_for_type("  #ff00aa  ", "color") == "#ff00aa"


def test_coerce_default_for_color_rejects_invalid():
    assert coerce_default_for_type("red", "color") == COLOR_DEFAULT
    assert coerce_default_for_type("#zz", "color") == COLOR_DEFAULT
    assert coerce_default_for_type("", "color") == COLOR_DEFAULT
    assert coerce_default_for_type("#ff00", "color") == COLOR_DEFAULT
    assert coerce_default_for_type("ffffff", "color") == COLOR_DEFAULT


def test_is_valid_hex_basic_cases():
    assert is_valid_hex("#abc")
    assert is_valid_hex("#ABC")
    assert is_valid_hex("#abcdef")
    assert is_valid_hex("#ABCDEF")
    assert not is_valid_hex("")
    assert not is_valid_hex("abc")
    assert not is_valid_hex("#")
    assert not is_valid_hex("#zzz")
    assert not is_valid_hex("#ff00")


def test_color_property_compat_includes_color_and_str():
    compat = compatible_var_types("color")
    assert "color" in compat
    assert "str" in compat


def test_non_color_property_excludes_color():
    text_compat = compatible_var_types("text")
    assert "color" not in text_compat
    bool_compat = compatible_var_types("boolean")
    assert "color" not in bool_compat
