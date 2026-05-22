import pytest

from app.core.widget_node import WidgetNode
from app.io.scripts import (
    add_handler_stub,
    find_handler_method,
    load_or_create_behavior_file,
    parse_handler_methods,
    parse_handler_methods_compatible,
    parse_method_docstrings,
    parse_module_functions,
    slugify_method_part,
    suggest_method_name,
)
from app.widgets.event_registry import event_by_key
from tests.conftest import StubDoc


# ---- slugify_method_part -------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("MyButton", "mybutton"),
        ("login form", "login_form"),
        ("multi   spaces", "multi_spaces"),
        ("trailing___", "trailing"),
        ("---leading", "leading"),
    ],
)
def test_slugify_method_part_known_inputs(raw, expected):
    assert slugify_method_part(raw) == expected


def test_slugify_method_part_prefixes_underscore_for_leading_digit():
    assert slugify_method_part("1foo") == "_1foo"


@pytest.mark.parametrize("raw", ["", None, "!!!", "   "])
def test_slugify_method_part_falls_back_to_x(raw):
    assert slugify_method_part(raw) == "x"


# ---- load_or_create_behavior_file ----------------------------------------

def _saved_project_path(tmp_path, name="demo.ctkproj"):
    project_file = tmp_path / name
    project_file.write_text("{}", encoding="utf-8")
    return project_file


def test_load_or_create_behavior_file_returns_none_when_unsaved():
    assert load_or_create_behavior_file(None, document=None) is None


def test_load_or_create_behavior_file_creates_skeleton_with_class(tmp_path):
    project_file = _saved_project_path(tmp_path)
    doc = StubDoc(name="Login")

    path = load_or_create_behavior_file(project_file, document=doc)

    assert path is not None
    assert path.is_file()
    body = path.read_text(encoding="utf-8")
    assert "class LoginPage:" in body
    assert 'def setup(self, window: "ctk.CTk | ctk.CTkToplevel") -> None:' in body


def test_load_or_create_behavior_file_returns_existing_path_unchanged(tmp_path):
    project_file = _saved_project_path(tmp_path)
    doc = StubDoc(name="Login")
    first = load_or_create_behavior_file(project_file, document=doc)
    first.write_text(
        "class LoginPage:\n    def setup(self, window):\n        pass\n"
        "    def custom_handler(self):\n        return 42\n",
        encoding="utf-8",
    )

    second = load_or_create_behavior_file(project_file, document=doc)

    assert second == first
    assert "custom_handler" in second.read_text(encoding="utf-8")


# ---- parse_handler_methods -----------------------------------------------

def test_parse_handler_methods_lists_class_methods(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    def setup(self, window): pass\n"
        "    def on_click(self): pass\n",
        encoding="utf-8",
    )

    assert parse_handler_methods(file, "LoginPage") == [
        "setup", "on_click",
    ]


def test_parse_handler_methods_returns_empty_for_missing_file(tmp_path):
    assert parse_handler_methods(tmp_path / "nope.py", "LoginPage") == []


def test_parse_handler_methods_returns_empty_for_missing_class(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text("class OtherPage:\n    pass\n", encoding="utf-8")

    assert parse_handler_methods(file, "LoginPage") == []


def test_parse_handler_methods_returns_empty_on_syntax_error(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text("class LoginPage(:\n    def broken(\n", encoding="utf-8")

    assert parse_handler_methods(file, "LoginPage") == []


def test_parse_handler_methods_includes_async_defs(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    async def fetch(self): pass\n"
        "    def sync_one(self): pass\n",
        encoding="utf-8",
    )

    assert parse_handler_methods(file, "LoginPage") == [
        "fetch", "sync_one",
    ]


# ---- parse_handler_methods_compatible ------------------------------------

def test_parse_compatible_command_keeps_zero_arg_methods(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    def setup(self, window): pass\n"
        "    def on_click(self): pass\n"
        "    def on_event(self, event): pass\n",
        encoding="utf-8",
    )

    # ``command`` events call method() — only zero-arg-after-self
    # methods qualify. ``setup`` has a required ``window`` arg, so
    # it's filtered out alongside the bind-shaped ``on_event``.
    assert parse_handler_methods_compatible(
        file, "LoginPage", "command",
    ) == ["on_click"]


def test_parse_compatible_bind_requires_one_positional_after_self(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    def on_click(self): pass\n"
        "    def on_event(self, event): pass\n"
        "    def on_default(self, event=None): pass\n",
        encoding="utf-8",
    )

    # ``bind`` events pass an event arg — methods need a slot for it.
    # ``on_click`` (zero positional after self) is filtered out.
    # ``on_default`` qualifies because the default-valued param
    # still accepts a positional event arg.
    assert parse_handler_methods_compatible(
        file, "LoginPage", "bind",
    ) == ["on_event", "on_default"]


def test_parse_compatible_drops_private_and_dunder(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    def public_one(self): pass\n"
        "    def _private(self): pass\n"
        "    def __dunder__(self): pass\n",
        encoding="utf-8",
    )

    assert parse_handler_methods_compatible(
        file, "LoginPage", "command",
    ) == ["public_one"]


def test_parse_compatible_unknown_wiring_kind_returns_empty(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n    def on_click(self): pass\n",
        encoding="utf-8",
    )

    assert parse_handler_methods_compatible(
        file, "LoginPage", "ghost_kind",
    ) == []


def test_parse_compatible_filters_reserved_setup_from_bind(tmp_path):
    """``setup(self, window)`` matches the ``bind`` signature shape
    (one positional after self) so without the reserved-set filter it
    leaks into every Label/Entry/Textbox bind picker. Other methods
    with the same signature shape but a non-reserved name (``helper``)
    must still pass through.
    """
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    def setup(self, window): pass\n"
        "    def on_label_click(self, event=None): pass\n"
        "    def helper(self, payload): pass\n",
        encoding="utf-8",
    )

    assert parse_handler_methods_compatible(
        file, "LoginPage", "bind",
    ) == ["on_label_click", "helper"]


# ---- parse_module_functions ----------------------------------------------

def test_parse_module_functions_lists_top_level_public_defs(tmp_path):
    file = tmp_path / "helpers.py"
    file.write_text(
        "def save_log():\n    pass\n"
        "def _private():\n    pass\n"
        "async def fetch():\n    pass\n"
        "class Helper:\n"
        "    def method(self): pass\n"
        "def outer():\n"
        "    def nested():\n        pass\n",
        encoding="utf-8",
    )

    # Public top-level sync ``def`` only — private, async,
    # nested, and class methods are all filtered.
    assert parse_module_functions(file) == ["save_log", "outer"]


def test_parse_module_functions_signature_filter_command(tmp_path):
    file = tmp_path / "helpers.py"
    file.write_text(
        "def zero_args():\n    pass\n"
        "def one_required(window):\n    pass\n"
        "def one_default(window=None):\n    pass\n",
        encoding="utf-8",
    )

    # Direct-binding convention: an argless command is called
    # ``helpers.func(window)`` — the function needs 1 positional slot
    # (the window) and at most 1 required arg. The 0-arg function no
    # longer qualifies (the window would be dropped).
    assert parse_module_functions(file, "command") == [
        "one_required", "one_default",
    ]


def test_parse_module_functions_signature_filter_bind(tmp_path):
    file = tmp_path / "helpers.py"
    file.write_text(
        "def zero_args():\n    pass\n"
        "def one_arg(window):\n    pass\n"
        "def window_event(window, event):\n    pass\n"
        "def window_event_default(window, event=None):\n    pass\n",
        encoding="utf-8",
    )

    # Direct-binding convention: bind handlers are called
    # ``func(window, event)`` — need 2 positional slots, at most 2
    # required. A 1-arg function no longer qualifies (the event would
    # be dropped).
    assert parse_module_functions(file, "bind") == [
        "window_event", "window_event_default",
    ]


def test_parse_module_functions_missing_file_returns_empty(tmp_path):
    assert parse_module_functions(tmp_path / "nope.py") == []


def test_parse_module_functions_syntax_error_returns_empty(tmp_path):
    file = tmp_path / "helpers.py"
    file.write_text("def broken(:\n", encoding="utf-8")

    assert parse_module_functions(file) == []


# ---- parse_method_docstrings ---------------------------------------------

def test_parse_method_docstrings_returns_first_line(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        'class LoginPage:\n'
        '    def setup(self, window):\n'
        '        """Stash refs.\n\n'
        '        Long description that should be ignored.\n'
        '        """\n'
        '    def on_click(self):\n'
        '        pass\n',
        encoding="utf-8",
    )

    docs = parse_method_docstrings(file, "LoginPage")

    assert docs == {"setup": "Stash refs."}


def test_parse_method_docstrings_empty_on_failure(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text("not python at all (((", encoding="utf-8")

    assert parse_method_docstrings(file, "LoginPage") == {}


# ---- find_handler_method -------------------------------------------------

def test_find_handler_method_returns_line_number(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    def setup(self, window): pass\n"
        "    def on_click(self): pass\n",
        encoding="utf-8",
    )

    assert find_handler_method(file, "LoginPage", "on_click") == 3


def test_find_handler_method_returns_none_when_missing(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n    def setup(self, window): pass\n",
        encoding="utf-8",
    )

    assert find_handler_method(file, "LoginPage", "ghost") is None


# ---- add_handler_stub ----------------------------------------------------

def test_add_handler_stub_appends_method_and_returns_line(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    def setup(self, window):\n"
        "        self.window = window\n",
        encoding="utf-8",
    )

    line = add_handler_stub(file, "LoginPage", "on_click", "(self)")

    assert isinstance(line, int) and line > 0
    body = file.read_text(encoding="utf-8")
    assert "def on_click(self):" in body
    assert body.count("def on_click") == 1
    # Reported line should land on the new ``def`` row.
    assert body.splitlines()[line - 1].strip().startswith("def on_click")


def test_add_handler_stub_idempotent_on_existing_method(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    def on_click(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )

    first = add_handler_stub(file, "LoginPage", "on_click", "(self)")
    body_after_first = file.read_text(encoding="utf-8")
    second = add_handler_stub(file, "LoginPage", "on_click", "(self)")

    assert first == second
    # No duplicate def written.
    assert file.read_text(encoding="utf-8") == body_after_first
    assert body_after_first.count("def on_click") == 1


def test_add_handler_stub_returns_none_for_missing_class(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text("class Other:\n    pass\n", encoding="utf-8")

    assert add_handler_stub(file, "LoginPage", "on_click") is None


def test_add_handler_stub_then_parse_includes_new_method(tmp_path):
    file = tmp_path / "behavior.py"
    file.write_text(
        "class LoginPage:\n"
        "    def setup(self, window): pass\n",
        encoding="utf-8",
    )

    add_handler_stub(file, "LoginPage", "on_click", "(self)")

    assert "on_click" in parse_handler_methods(file, "LoginPage")
    assert find_handler_method(file, "LoginPage", "on_click") is not None


# ---- suggest_method_name -------------------------------------------------

class _FakeDoc:
    """Minimal stand-in for ``Document`` that ``collect_used_method_names``
    walks: needs ``.root_widgets`` (list of WidgetNode-shaped objects)."""

    def __init__(self, root_widgets=None):
        self.root_widgets = list(root_widgets or [])


def test_suggest_method_name_uses_widget_slug_and_verb():
    button = WidgetNode("CTkButton")
    button.name = "Login Button"
    doc = _FakeDoc([button])
    entry = event_by_key("CTkButton", "command")

    assert suggest_method_name(button, entry, doc) == "on_login_button_click"


def test_suggest_method_name_falls_back_to_widget_type_when_no_name():
    button = WidgetNode("CTkButton")
    doc = _FakeDoc([button])
    entry = event_by_key("CTkButton", "command")

    assert suggest_method_name(button, entry, doc) == "on_ctkbutton_click"


def test_suggest_method_name_appends_numeric_suffix_on_collision():
    existing = WidgetNode("CTkButton")
    existing.name = "Submit"
    existing.handlers = {"command": ["on_submit_click", "on_submit_click_2"]}
    new_button = WidgetNode("CTkButton")
    new_button.name = "Submit"
    doc = _FakeDoc([existing, new_button])
    entry = event_by_key("CTkButton", "command")

    assert suggest_method_name(new_button, entry, doc) == "on_submit_click_3"
