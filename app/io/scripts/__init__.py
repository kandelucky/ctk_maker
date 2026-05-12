"""Read / write the per-window behavior file.

A behavior file holds the user-written Python that backs widget event
handlers. CTkMaker generates method skeletons; the user writes the
bodies in their own editor. The file lives at
``<project>/assets/scripts/<page>/<window>.py`` (one per Document)
and is imported by exported code as
``from assets.scripts.<page>.<window> import <WindowName>Page``.

Object References (v1.10.8+) — annotated class attributes typed as
``ref[<WidgetType>]`` declare Inspector slots that pair with entries
in the document's ``local_object_references``. Resolution happens at
export time via ``self._behavior.<field> = self.<widget_var>`` lines
after ``_build_ui()``. The ``ref`` marker class lives in an
auto-generated ``assets/scripts/_runtime.py`` so behavior files stay
importable outside CTkMaker (IDE typing, standalone tests, etc.).

Sub-modules group helpers by what they do; this package re-exports
the public surface so existing callers can keep importing from
``app.io.scripts``.
"""

from app.io.scripts.ast_scan import (
    FieldSpec,
    existing_object_reference_names,
    find_handler_method,
    parse_handler_methods,
    parse_method_docstrings,
    parse_object_reference_fields,
)
from app.io.scripts.editor import (
    launch_editor,
    resolve_project_root_for_editor,
)
from app.io.scripts.mutate import (
    add_handler_stub,
    add_object_reference_annotation,
    collect_used_method_names,
    delete_method_from_file,
    delete_object_reference_annotation,
    ensure_imports_in_behavior_file,
    ensure_relative_import_in_behavior_file,
    slugify_method_part,
    suggest_method_name,
    suggest_object_reference_name,
)
from app.io.scripts.paths import (
    load_or_create_behavior_file,
    recycle_behavior_file,
    rename_behavior_file_and_class,
    save_behavior_file_copy,
)
from app.io.scripts.runtime import ensure_runtime_helpers

__all__ = [
    # ast_scan
    "FieldSpec",
    "existing_object_reference_names",
    "find_handler_method",
    "parse_handler_methods",
    "parse_method_docstrings",
    "parse_object_reference_fields",
    # editor
    "launch_editor",
    "resolve_project_root_for_editor",
    # mutate
    "add_handler_stub",
    "add_object_reference_annotation",
    "collect_used_method_names",
    "delete_method_from_file",
    "delete_object_reference_annotation",
    "ensure_imports_in_behavior_file",
    "ensure_relative_import_in_behavior_file",
    "slugify_method_part",
    "suggest_method_name",
    "suggest_object_reference_name",
    # paths
    "load_or_create_behavior_file",
    "recycle_behavior_file",
    "rename_behavior_file_and_class",
    "save_behavior_file_copy",
    # runtime
    "ensure_runtime_helpers",
]
