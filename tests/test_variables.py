from app.core.variables import (
    COLOR_DEFAULT,
    VAR_TYPES,
    VariableEntry,
    coerce_default_for_type,
    compatible_var_types,
    eligible_variables,
    is_valid_hex,
    var_type_accepts,
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


# -- script field ↔ variable type compatibility (Q5 / A1) -------------

def test_var_type_accepts_exact_match():
    assert var_type_accepts("str", "str")
    assert var_type_accepts("int", "int")
    assert var_type_accepts("float", "float")
    assert var_type_accepts("bool", "bool")


def test_var_type_accepts_str_field_takes_color():
    # A1: a tk.StringVar field also accepts color variables.
    assert var_type_accepts("str", "color")


def test_var_type_accepts_rejects_cross_type():
    assert not var_type_accepts("int", "color")
    assert not var_type_accepts("int", "str")
    assert not var_type_accepts("bool", "int")
    assert not var_type_accepts("float", "int")


def test_eligible_variables_filters_and_orders():
    g_int = VariableEntry(name="score", type="int", scope="global")
    g_col = VariableEntry(name="accent", type="color", scope="global")
    g_str = VariableEntry(name="title", type="str", scope="global")
    l_int = VariableEntry(name="count", type="int", scope="local")
    l_col = VariableEntry(name="bg", type="color", scope="local")
    globals_ = [g_int, g_col, g_str]
    locals_ = [l_int, l_col]

    # str field → str + color, globals before locals.
    assert [v.name for v in eligible_variables(globals_, locals_, "str")] == [
        "accent", "title", "bg",
    ]
    # int field → only int variables.
    assert [v.name for v in eligible_variables(globals_, locals_, "int")] == [
        "score", "count",
    ]


def test_eligible_variables_empty():
    assert eligible_variables([], [], "bool") == []
