"""Library script creation — template content guarantees.

``create_library_script`` writes a small skeleton at the page-folder
root. Tests verify the upgraded v1.41.7 template ships:

* module-level docstring explaining usage
* ``from __future__ import annotations`` for forward-typed signatures
* a placeholder ``example`` function with a docstring telling the user
  to replace it
"""

from __future__ import annotations

from pathlib import Path

from app.io.library_scripts import create_library_script


def _scaffold_project(tmp_path: Path) -> Path:
    """Build the minimum disk layout ``create_library_script`` requires:
    a ``project.json`` at the project root plus the page ``.ctkproj``
    that scripts attach to. Returns the page-file path.
    """
    pages = tmp_path / "assets" / "pages"
    pages.mkdir(parents=True)
    page_path = pages / "main.ctkproj"
    page_path.write_text("{}", encoding="utf-8")
    (tmp_path / "project.json").write_text(
        '{"version": 1, "pages": [{"id": "p1", "file": "main.ctkproj"}]}',
        encoding="utf-8",
    )
    return page_path


def test_create_library_script_writes_docstring_and_future_import(tmp_path):
    page_path = _scaffold_project(tmp_path)

    target = create_library_script(str(page_path), "helpers")

    assert target is not None
    assert target.is_file()
    body = target.read_text(encoding="utf-8")
    assert body.startswith('"""Library script for this page.')
    assert "from __future__ import annotations" in body


def test_create_library_script_writes_example_placeholder(tmp_path):
    page_path = _scaffold_project(tmp_path)

    target = create_library_script(str(page_path), "helpers")

    body = target.read_text(encoding="utf-8")
    assert "def example() -> None:" in body
    assert "Replace with your own function." in body


def test_create_library_script_supports_subfolder(tmp_path):
    """Sub-package paths (``services/auth``) are an existing capability
    — extending the template must not break that path.
    """
    page_path = _scaffold_project(tmp_path)

    target = create_library_script(str(page_path), "services/auth")

    assert target is not None
    assert target.is_file()
    assert target.name == "auth.py"
    body = target.read_text(encoding="utf-8")
    assert "from __future__ import annotations" in body
