from app.widgets.circular_progress import CircularProgressDescriptor, _RUNTIME_KWARGS


# ------------------------------------------------------------------
# Descriptor defaults
# ------------------------------------------------------------------

def test_default_suffix():
    assert CircularProgressDescriptor.default_properties["suffix"] == "%"


def test_default_font_family():
    assert CircularProgressDescriptor.default_properties["font_family"] == "TkDefaultFont"


def test_no_text_format_in_defaults():
    assert "text_format" not in CircularProgressDescriptor.default_properties


# ------------------------------------------------------------------
# _RUNTIME_KWARGS membership
# ------------------------------------------------------------------

def test_suffix_in_runtime_kwargs():
    assert "suffix" in _RUNTIME_KWARGS


def test_font_family_in_runtime_kwargs():
    assert "font_family" in _RUNTIME_KWARGS


def test_text_format_not_in_runtime_kwargs():
    assert "text_format" not in _RUNTIME_KWARGS


# ------------------------------------------------------------------
# transform_properties
# ------------------------------------------------------------------

def test_transform_passes_suffix():
    props = {**CircularProgressDescriptor.default_properties}
    result = CircularProgressDescriptor.transform_properties(props)
    assert "suffix" in result
    assert result["suffix"] == "%"


def test_transform_passes_font_family():
    props = {**CircularProgressDescriptor.default_properties}
    result = CircularProgressDescriptor.transform_properties(props)
    assert "font_family" in result


def test_transform_strips_x_y():
    props = {**CircularProgressDescriptor.default_properties, "x": 10, "y": 20}
    result = CircularProgressDescriptor.transform_properties(props)
    assert "x" not in result
    assert "y" not in result


def test_transform_strips_unknown_keys():
    props = {**CircularProgressDescriptor.default_properties, "bogus": "value"}
    result = CircularProgressDescriptor.transform_properties(props)
    assert "bogus" not in result


# ------------------------------------------------------------------
# "none" suffix rendering logic (isolated — no Tk required)
# ------------------------------------------------------------------

def _render_suffix(suffix: str) -> str:
    return "" if suffix == "none" else suffix


def test_none_suffix_renders_empty():
    assert _render_suffix("none") == ""


def test_percent_suffix_passes_through():
    assert _render_suffix("%") == "%"


def test_degree_suffix_passes_through():
    assert _render_suffix("°") == "°"


def test_celsius_suffix_passes_through():
    assert _render_suffix("°C") == "°C"


def test_custom_suffix_passes_through():
    assert _render_suffix("rpm") == "rpm"


def test_text_format_with_suffix(suffix="%", percent=75):
    sfx = _render_suffix(suffix)
    assert f"{percent}{sfx}" == "75%"


def test_text_format_with_none_suffix(percent=75):
    sfx = _render_suffix("none")
    assert f"{percent}{sfx}" == "75"
