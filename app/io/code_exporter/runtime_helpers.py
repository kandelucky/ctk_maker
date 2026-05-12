"""Runtime helper text for the exported `.py` file.

Each `*_lines()` function returns a list of source lines spliced into
the generated file's helper preamble. Two flavours:

- Inline runtime classes (``CircleButton`` / ``CircleLabel`` /
  ``CircularProgress``) — read live source via ``inspect.getsource``
  so a single edit in ``app/widgets/runtime/`` propagates to every
  export.
- Hand-written helpers (``_wire_icon_state``, ``_align_text_label``,
  ``_setup_text_clipboard``, ``_auto_hover_text``,
  ``_register_project_fonts``, ``_tint_image``) — string literals
  kept here because the runtime they target doesn't need a builder-
  side equivalent.
"""

from __future__ import annotations


def _circle_button_class_lines() -> list[str]:
    """Inline the ``CircleButton`` runtime class (CTkButton override
    that lifts the rounded-corner reservation in ``_create_grid``) into
    generated ``.py`` files. Source lives at
    ``app/widgets/runtime/circle_button.py`` for builder use; reading
    via ``inspect`` keeps a single edit propagating to every export.
    The standard import block already covers ``customtkinter as ctk``.
    """
    import inspect

    from app.widgets.runtime.circle_button import CircleButton

    return inspect.getsource(CircleButton).splitlines()


def _circle_label_class_lines() -> list[str]:
    """Inline the ``CircleLabel`` runtime class (CTkLabel override
    that zeroes the rounded-corner padx in ``_create_grid``) into
    generated ``.py`` files. Source lives at
    ``app/widgets/runtime/circle_label.py`` for builder use; reading
    via ``inspect`` keeps a single edit propagating to every export.
    The standard import block already covers ``customtkinter as ctk``.
    """
    import inspect

    from app.widgets.runtime.circle_label import CircleLabel

    return inspect.getsource(CircleLabel).splitlines()


def _circular_progress_class_lines() -> list[str]:
    """Inline the ``CircularProgress`` runtime class + its bg-resolver
    helper into generated `.py` files. The class lives in
    ``app/widgets/runtime/circular_progress.py`` for builder use; we
    read its source via ``inspect`` so a single edit propagates to
    every export. The runtime module's own ``tkinter as tk`` /
    ``customtkinter as ctk`` imports are already emitted by the
    standard import block; ``CTkScalingBaseClass`` is a deeper CTk
    internal path that the standard imports don't cover, so we emit
    it here as a sibling of the helper + class definitions.
    """
    import inspect

    from app.widgets.runtime.circular_progress import (
        CircularProgress,
        _circular_progress_resolve_bg,
    )

    lines: list[str] = [
        "from customtkinter.windows.widgets.scaling import "
        "CTkScalingBaseClass",
        "",
    ]
    lines.extend(
        inspect.getsource(_circular_progress_resolve_bg).splitlines(),
    )
    lines.append("")
    lines.append("")
    lines.extend(inspect.getsource(CircularProgress).splitlines())
    return lines


def _icon_state_helper_lines() -> list[str]:
    """Emit ``_wire_icon_state`` — wraps ``button.configure`` so that
    any later ``configure(state=...)`` also swaps the tinted image
    variant. CTk's native state change doesn't touch the image, so
    without this wrapper a disabled-tint icon never appears at runtime
    even though the constructor emitted both variants.
    """
    return [
        "def _wire_icon_state(button, icon_on, icon_off):",
        '    """Auto-sync a CTkButton\'s icon with its state.',
        "    After wiring, ``button.configure(state=...)`` swaps the",
        "    tinted image variant automatically. An explicit ``image=``",
        '    in the same call wins over the auto-pick."""',
        "    original_configure = button.configure",
        "    def configure(*args, **kwargs):",
        '        if "state" in kwargs and "image" not in kwargs:',
        '            kwargs["image"] = (',
        '                icon_off if kwargs["state"] == "disabled" else icon_on',
        "            )",
        "        return original_configure(*args, **kwargs)",
        "    button.configure = configure",
    ]


def _align_text_label_helper_lines() -> list[str]:
    """Emit a helper that re-grids the internal `_canvas` (box / dot)
    and `_text_label` of any compound widget that follows the
    CheckBox / RadioButton / Switch grid layout. Lets the label sit
    on any side (left / top / bottom — right is CTk's default and
    a no-op). Same private-attr reach the builder uses at design
    time so canvas = preview = exported runtime.
    """
    return [
        "def _align_text_label(widget, position, spacing=6):",
        '    """Re-grid the checkbox box + label so the label sits at',
        "    `position` (left / right / top / bottom) with `spacing` px",
        "    between them. Same private-attr reach the CTk Visual",
        '    Builder uses at design time."""',
        '    canvas = getattr(widget, "_canvas", None)',
        '    label = getattr(widget, "_text_label", None)',
        '    bg = getattr(widget, "_bg_canvas", None)',
        "    if canvas is None or label is None: return",
        "    s = max(0, int(spacing))",
        "    canvas.grid_forget(); label.grid_forget()",
        "    if bg is not None: bg.grid_forget()",
        '    if position == "left":',
        '        if bg is not None: bg.grid(row=0, column=0, columnspan=3, sticky="nswe")',
        '        label.grid(row=0, column=0, sticky="e", padx=(0, s)); canvas.grid(row=0, column=2, sticky="w")',
        '        label["anchor"] = "e"',
        '    elif position == "top":',
        '        if bg is not None: bg.grid(row=0, column=0, rowspan=3, columnspan=3, sticky="nswe")',
        '        label.grid(row=0, column=0, sticky="s", pady=(0, s)); canvas.grid(row=2, column=0, sticky="n")',
        '        label["anchor"] = "center"',
        '    elif position == "bottom":',
        '        if bg is not None: bg.grid(row=0, column=0, rowspan=3, columnspan=3, sticky="nswe")',
        '        canvas.grid(row=0, column=0, sticky="s"); label.grid(row=2, column=0, sticky="n", pady=(s, 0))',
        '        label["anchor"] = "center"',
        "    else:",
        '        if bg is not None: bg.grid(row=0, column=0, columnspan=3, sticky="nswe")',
        '        canvas.grid(row=0, column=0, sticky="e"); label.grid(row=0, column=2, sticky="w", padx=(s, 0))',
        '        label["anchor"] = "w"',
    ]


def _text_clipboard_helper_lines() -> list[str]:
    """Emit a helper that wires right-click context menus and a
    keycode-based Ctrl shortcut router onto every tk.Entry / tk.Text
    widget. Lets the exported app's text fields support Cut / Copy /
    Paste / Select All via mouse AND keyboard, regardless of the
    user's keyboard layout (Latin keysyms break under non-Latin
    layouts; hardware keycodes don't).
    """
    return [
        "def _setup_text_clipboard(root):",
        '    """Add right-click menu and keyboard shortcuts to all text fields."""',
        "    import sys",
        "    import tkinter as tk",
        '    # Resolve at runtime so the exported app adapts to the END',
        "    # USER's platform — not the platform that ran the exporter.",
        '    _mod_key = "Command" if sys.platform == "darwin" else "Control"',
        "    def _popup(event):",
        "        widget = event.widget",
        "        # tk.Entry uses .selection_present(); tk.Text uses",
        '        # .tag_ranges("sel"). Try both, default off.',
        "        has_sel = False",
        "        try: has_sel = bool(widget.selection_present())",
        "        except Exception:",
        "            try: has_sel = bool(widget.tag_ranges(\"sel\"))",
        "            except Exception: has_sel = False",
        "        menu = tk.Menu(widget, tearoff=0)",
        '        menu.add_command(label="Cut",   state=("normal" if has_sel else "disabled"),  command=lambda: widget.event_generate("<<Cut>>"))',
        '        menu.add_command(label="Copy",  state=("normal" if has_sel else "disabled"),  command=lambda: widget.event_generate("<<Copy>>"))',
        '        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))',
        "        menu.add_separator()",
        '        menu.add_command(label="Select All", command=lambda: widget.event_generate("<<SelectAll>>"))',
        "        try: menu.tk_popup(event.x_root, event.y_root)",
        "        finally: menu.grab_release()",
        "    def _ctrl(event):",
        "        # Latin layouts (V/C/X/A keysym) hit tk's defaults — skip.",
        '        if event.keysym.lower() in ("v", "c", "x", "a"): return None',
        "        kc = event.keycode",
        '        if kc == 86: event.widget.event_generate("<<Paste>>"); return "break"',
        '        if kc == 67: event.widget.event_generate("<<Copy>>");  return "break"',
        '        if kc == 88: event.widget.event_generate("<<Cut>>");   return "break"',
        '        if kc == 65:',
        '            try: event.widget.event_generate("<<SelectAll>>")',
        "            except Exception: pass",
        '            return "break"',
        '    for cls in ("Entry", "Text"):',
        '        root.bind_class(cls, "<Button-3>", _popup, add="+")',
        '        root.bind_class(cls, f"<{_mod_key}-KeyPress>", _ctrl, add="+")',
        "    # Clicks on non-text widgets (Frame, root, Button, etc.)",
        "    # force focus to the root so any previously-focused",
        "    # Entry / Text fires FocusOut — that's what CTk relies on",
        "    # to restore its placeholder when the field is empty.",
        "    # Without this the caret stays blinking in an Entry even",
        "    # after the user clicked somewhere else.",
        "    def _focus_restore(event):",
        "        target = event.widget",
        "        if isinstance(target, (tk.Entry, tk.Text)):",
        "            return",
        "        # Defer by one tick so the clicked widget's own focus",
        "        # handling runs first; if it takes focus, we stay out",
        "        # of its way. Otherwise focus lands on the root and",
        "        # any Entry picks up its FocusOut.",
        "        try: root.after(1, root.focus_set)",
        "        except Exception: pass",
        '    root.bind_all("<Button-1>", _focus_restore, add="+")',
    ]


def _auto_hover_text_helper_lines() -> list[str]:
    """Emit a tiny module-level helper that wires <Enter>/<Leave> on a
    button to swap its text colour. CTk's native hover only retints
    the background; this gives the label its own reactive feel.
    Reaches into ``_text_label`` directly so it doesn't trip CTk's
    full configure pipeline (which would reset the hover background
    mid-hover).
    """
    return [
        "def _auto_hover_text(button, normal, hover):",
        '    """Bind <Enter>/<Leave> to swap text_color. Same lighten/darken',
        "    direction CTkMaker uses at design time so the",
        '    runtime feel matches the canvas preview."""',
        "    def _set(colour):",
        '        lbl = getattr(button, "_text_label", None)',
        "        if lbl is not None:",
        "            lbl.configure(fg=colour)",
        '    button.bind("<Enter>", lambda e: _set(hover))',
        '    button.bind("<Leave>", lambda e: _set(normal))',
    ]


def _font_register_helper_lines() -> list[str]:
    """Emit a module-level helper that loads every ``.ttf`` / ``.otf``
    sitting in ``assets/fonts/`` next to the script via tkextrafont
    so ``CTkFont(family=...)`` resolves the bundled families. Soft
    dependency — if tkextrafont isn't installed, the helper logs and
    falls back to Tk defaults so the rest of the app still runs.
    """
    return [
        "def _register_project_fonts(root):",
        '    """Load every .ttf / .otf in assets/fonts/ next to this',
        "    script so widget CTkFont(family=...) lookups can find",
        '    families bundled with the project."""',
        "    from pathlib import Path",
        '    fonts_dir = Path(__file__).resolve().parent / "assets" / "fonts"',
        "    if not fonts_dir.exists():",
        "        return",
        "    try:",
        "        from tkextrafont import Font",
        "    except ImportError:",
        "        # tkextrafont missing — bundled fonts won't load, but",
        "        # system / Tk-default fonts still render.",
        "        return",
        '    for f in sorted(fonts_dir.iterdir()):',
        '        if f.suffix.lower() in (".ttf", ".otf", ".ttc"):',
        "            try:",
        "                Font(root, file=str(f))",
        "            except Exception:",
        "                pass",
    ]


def _tint_helper_lines() -> list[str]:
    """Emit a module-level helper that tints a PNG with an RGB hex
    color while preserving the source alpha channel. Used by every
    widget whose ``image_color`` is set (Image + CTkButton-style
    icon tint). Matches the builder's preview tint so the exported
    app renders identically.
    """
    return [
        "def _tint_image(path, hex_color, size):",
        '    """Return a CTkImage whose pixels are recoloured to `hex_color`',
        "    while keeping the source PNG's alpha. Same tint logic the CTk",
        '    Visual Builder uses at design time."""',
        "    src = Image.open(path).convert(\"RGBA\")",
        "    r = int(hex_color[1:3], 16)",
        "    g = int(hex_color[3:5], 16)",
        "    b = int(hex_color[5:7], 16)",
        "    alpha = src.split()[-1]",
        "    tinted = Image.new(\"RGBA\", src.size, (r, g, b, 255))",
        "    tinted.putalpha(alpha)",
        "    return ctk.CTkImage(",
        "        light_image=tinted, dark_image=tinted, size=size,",
        "    )",
    ]
