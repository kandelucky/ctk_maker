"""Runtime helper templates spliced into generated `.py` files when a
project uses variable bindings the auto-trace path covers.

Each `_AUTO_TRACE_*_HELPER` is a triple-quoted Python source string —
they're emitted verbatim into the exported file's helper preamble,
not invoked here. The composite key sets and `_FONT_COMPOSITE_TO_ATTR`
map drive the gates in ``_emit_auto_trace_bindings`` and the
``_project_needs_auto_trace_*_helper`` detection functions, deciding
which helper strings to splice into each export.

`_PACK_BALANCE_HELPER` is a sibling template for the flex-pack
shrink-fit runtime used by vbox / hbox layouts.
"""

from __future__ import annotations


_AUTO_TRACE_WIDGET_HELPER = '''def _bind_var_to_widget(var, widget, prop):
    """Mirror ``var.get()`` into ``widget.configure(prop=…)`` whenever
    the variable changes. Initial sync on attach so the widget paints
    the var's current value even if the constructor kwarg already set
    it to the same literal.
    """
    def _update(*_):
        widget.configure(**{prop: var.get()})
    var.trace_add("write", _update)
    _update()
'''

_AUTO_TRACE_TEXTBOX_HELPER = '''def _bind_var_to_textbox(var, tb):
    """Mirror ``var.get()`` into a CTkTextbox's content via
    delete+insert. CTkTextbox has no ``textvariable=`` support, so
    every change rewrites the whole buffer.
    """
    def _update(*_):
        tb.delete("1.0", "end")
        tb.insert("1.0", var.get())
    var.trace_add("write", _update)
    _update()
'''

# Phase 1 of the live composite bindings plan — Maker-only composite
# keys (font_bold / font_italic / font_size / font_family) don't map
# to CTk's ``configure(...)`` because Maker decomposes them into a
# single ``CTkFont`` instance at construction. The helper rebuilds
# the font when the var changes, preserving the other five font
# attributes so a bold toggle doesn't also reset size / italic.
_AUTO_TRACE_FONT_HELPER = '''def _bind_var_to_font(var, widget, attr):
    """Rebuild ``widget``'s CTkFont when ``var`` changes — for
    font_bold / font_italic / font_size / font_family bindings.
    ``attr`` is the CTkFont kwarg to update ("weight", "slant",
    "size", "family"); the other five font attributes are
    preserved so a bold toggle doesn't also reset size or italic.
    """
    def _update(*_):
        current = widget.cget("font")
        kwargs = dict(
            family=current.cget("family"),
            size=current.cget("size"),
            weight=current.cget("weight"),
            slant=current.cget("slant"),
            underline=current.cget("underline"),
            overstrike=current.cget("overstrike"),
        )
        value = var.get()
        if attr == "weight":
            kwargs["weight"] = "bold" if value else "normal"
        elif attr == "slant":
            kwargs["slant"] = "italic" if value else "roman"
        elif attr == "size":
            kwargs["size"] = int(value)
        elif attr == "family":
            kwargs["family"] = str(value)
        elif attr == "underline":
            kwargs["underline"] = bool(value)
        elif attr == "overstrike":
            kwargs["overstrike"] = bool(value)
        else:
            return
        widget.configure(font=ctk.CTkFont(**kwargs))
    var.trace_add("write", _update)
    _update()
'''

# Maker-only composite property keys that the font helper handles —
# map each property to the corresponding CTkFont kwarg name. Used by
# ``_emit_auto_trace_bindings`` to recognise font composites and
# emit ``_bind_var_to_font`` calls instead of the (broken-for-them)
# ``_bind_var_to_widget`` path.
_FONT_COMPOSITE_TO_ATTR = {
    "font_bold": "weight",
    "font_italic": "slant",
    "font_size": "size",
    "font_family": "family",
    "font_underline": "underline",
    "font_overstrike": "overstrike",
}

# Phase 3 + 4a — image-related Maker-only composites that all rebuild
# a fresh CTkImage from the widget's ``_maker_image_state`` dict.
# Membership is used by ``_emit_auto_trace_bindings`` to decide
# whether the widget needs the state-dict init prelude.
_IMAGE_REBUILD_KEYS = frozenset({
    "image", "image_width", "image_height", "preserve_aspect",
    "image_color", "image_color_disabled",
})

# Phase 3 — geometry composites driven through ``place_configure``.
_PLACE_COORD_KEYS = frozenset({"x", "y"})

# Phase 2a of live composite bindings — ``button_enabled`` is a Maker-
# only bool that maps to CTk's native ``state="normal"/"disabled"`` at
# construction time. The auto-trace path can't use ``_bind_var_to_widget``
# directly because the var holds True/False, not the string CTk wants;
# this helper does the bool→state mapping on every var write. Applies
# to ``CTkButton`` and every other CTk widget that exposes ``state=``
# (Entry / ComboBox / OptionMenu / Switch / CheckBox / RadioButton /
# Slider / SegmentedButton / Textbox / Card).
_AUTO_TRACE_STATE_HELPER = '''def _bind_var_to_state(var, widget):
    """Map ``var.get()`` (bool) to ``widget.configure(state=…)``.
    True → "normal", False → "disabled". Used for ``button_enabled``
    bindings where the variable type is bool but CTk's kwarg is a
    string enum. Also syncs ``widget._maker_image_state["enabled"]``
    so an image-tint binding paired with this state binding switches
    between ``color`` / ``color_disabled`` automatically.
    """
    def _update(*_):
        enabled = bool(var.get())
        widget.configure(state="normal" if enabled else "disabled")
        s = getattr(widget, "_maker_image_state", None)
        if s is not None and s.get("enabled") != enabled:
            s["enabled"] = enabled
            _rebuild_image_for_widget(widget)
    var.trace_add("write", _update)
    _update()
'''

# Maker-only bool composites that translate to CTk's ``state`` kwarg.
# Currently just ``button_enabled``; ``label_enabled`` has its own
# rebuilder (text_color swap) because Tk Label's native disabled
# rendering paints a stipple wash over the image.
_STATE_COMPOSITE_KEYS = frozenset({"button_enabled"})

# Phase 2b of live composite bindings — ``label_enabled`` (CTkLabel)
# doesn't use Tk's ``state="disabled"`` because the native disabled
# render paints a stipple wash over ``image=``; instead, Maker swaps
# ``text_color`` with ``text_color_disabled`` for the visual cue.
# The runtime rebuilder mirrors the same swap on var write — both
# colors are captured as literals at emit time and held in the
# closure, so toggling back to enabled restores the original
# ``text_color`` (rather than reading whatever the widget currently
# has, which would be the disabled color after the first toggle).
_AUTO_TRACE_LABEL_ENABLED_HELPER = '''def _bind_var_to_label_enabled(var, widget, color_on, color_off):
    """Map ``var.get()`` (bool) to a CTkLabel text_color swap.
    True → ``color_on``, False → ``color_off``. Used for
    ``label_enabled`` bindings — Tk Label's native disabled rendering
    paints a stipple wash over ``image=``, so we don't use
    ``state="disabled"``; we just swap colors. Also syncs
    ``widget._maker_image_state["enabled"]`` so an icon tint paired
    with ``image_color_disabled`` flips simultaneously.
    """
    def _update(*_):
        enabled = bool(var.get())
        widget.configure(text_color=color_on if enabled else color_off)
        s = getattr(widget, "_maker_image_state", None)
        if s is not None and s.get("enabled") != enabled:
            s["enabled"] = enabled
            _rebuild_image_for_widget(widget)
    var.trace_add("write", _update)
    _update()
'''

# Phase 2d — ``font_wrap`` (CTkLabel) drives whether the label wraps
# text. Maker's convention: ``font_wrap=True`` with ``wraplength=0``
# derives wraplength from the widget's current width minus 8px of
# breathing room; ``font_wrap=False`` disables wrapping by setting
# wraplength=0 (CTk's "don't wrap"). The rebuilder reads the widget's
# current width on every var write, so a label that gets resized
# between toggles still wraps to the right width.
_AUTO_TRACE_FONT_WRAP_HELPER = '''def _bind_var_to_font_wrap(var, widget):
    """Map ``var.get()`` (bool) to a CTkLabel wraplength swap.
    True → derive ``wraplength`` from the widget's current width
    (minus 8px breathing room); False → ``wraplength=0`` (no wrap).
    Mirrors Maker's editor-time behavior for ``font_wrap`` on
    CTkLabel; no analogue on CTkButton (which doesn't expose wrap).
    """
    def _update(*_):
        if var.get():
            try:
                w = int(widget.cget("width") or 100)
            except (TypeError, ValueError):
                w = 100
            widget.configure(wraplength=max(1, w - 8))
        else:
            widget.configure(wraplength=0)
    var.trace_add("write", _update)
    _update()
'''

# Phase 3 — ``x`` / ``y`` (geometry) are applied via ``widget.place()``
# at construction; the rebuilder calls ``place_configure(x=…)`` /
# ``place_configure(y=…)`` on var write so position can be driven
# live from a variable. Only meaningful for widgets using the
# ``place`` layout; widgets in pack / grid get no visible effect
# (place_configure on a non-place widget silently does nothing).
_AUTO_TRACE_PLACE_COORD_HELPER = '''def _bind_var_to_place_coord(var, widget, axis):
    """Map ``var.get()`` (int / float) to ``widget.place_configure(x=…)``
    or ``place_configure(y=…)`` depending on ``axis``. No-op for
    widgets not using place layout.
    """
    def _update(*_):
        try:
            val = int(var.get())
        except (TypeError, ValueError):
            return
        try:
            widget.place_configure(**{axis: val})
        except Exception:
            pass
    var.trace_add("write", _update)
    _update()
'''

# Phase 3 — image rebuilders (path / width / height / preserve_aspect)
# all converge on a single rebuild path that constructs a fresh
# CTkImage from the widget's current ``_maker_image_state`` dict. The
# state dict is populated at construction time and updated by each
# helper before rebuild. The construction-time tint / size logic is
# preserved so var-driven changes don't regress the static visual.
_AUTO_TRACE_IMAGE_REBUILD_HELPER = '''def _rebuild_image_for_widget(widget):
    """Rebuild ``widget``'s CTkImage from ``widget._maker_image_state``.
    Called by every image-param bind helper after it updates the
    relevant key. State dict keys:
        path                — file path (str)
        width / height      — int
        color               — normal tint hex (or None)
        color_disabled      — disabled tint hex (or None) — Phase 4a
        enabled             — bool (True → use color, False → use color_disabled)
        aspect              — bool (preserve aspect inside width × height)
    Honours ``preserve_aspect`` by fitting the image inside
    (width, height); otherwise stretches to (width, height).
    """
    from PIL import Image as _PILImage
    s = getattr(widget, "_maker_image_state", None)
    if not s:
        return
    path = s.get("path") or ""
    if not path:
        return
    try:
        width = max(1, int(s.get("width") or 20))
        height = max(1, int(s.get("height") or 20))
    except (TypeError, ValueError):
        width, height = 20, 20
    if not s.get("enabled", True) and s.get("color_disabled"):
        active_color = s.get("color_disabled")
    else:
        active_color = s.get("color")
    aspect = bool(s.get("aspect", False))
    try:
        if aspect:
            base = _PILImage.open(path)
            nw, nh = base.size
            scale = min(width / nw, height / nh)
            size = (max(1, int(nw * scale)), max(1, int(nh * scale)))
        else:
            size = (width, height)
        if active_color and active_color != "transparent":
            try:
                widget.configure(
                    image=_tint_image(path, active_color, size),
                )
            except NameError:
                # _tint_image not in scope for projects that only need
                # image rebuilds without tint. Fall back to untinted.
                widget.configure(image=ctk.CTkImage(
                    light_image=_PILImage.open(path),
                    dark_image=_PILImage.open(path),
                    size=size,
                ))
        else:
            widget.configure(image=ctk.CTkImage(
                light_image=_PILImage.open(path),
                dark_image=_PILImage.open(path),
                size=size,
            ))
    except Exception:
        pass


def _bind_var_to_image_path(var, widget):
    """Map ``var.get()`` (str path) to the widget's image. Path is
    looked up via ``widget._maker_image_state["path"]`` so the rebuild
    helper reuses size + tint + aspect from the same dict.
    """
    def _update(*_):
        s = getattr(widget, "_maker_image_state", None)
        if s is not None:
            s["path"] = var.get() or ""
            _rebuild_image_for_widget(widget)
    var.trace_add("write", _update)
    _update()


def _bind_var_to_image_color_state(var, widget, key):
    """Phase 4a — map ``var.get()`` to ``_maker_image_state[key]``
    (``"color"`` or ``"color_disabled"``) and trigger a rebuild.
    Picks the right shared rebuild path so changing the normal
    tint, the disabled tint, or the enabled flag all converge.
    """
    def _update(*_):
        s = getattr(widget, "_maker_image_state", None)
        if s is None:
            return
        s[key] = var.get() or None
        _rebuild_image_for_widget(widget)
    var.trace_add("write", _update)
    _update()


def _bind_var_to_image_size(var, widget, axis):
    """Map ``var.get()`` (int) to one image dimension. ``axis`` is
    ``"width"`` or ``"height"``; the other dimension and tint / aspect
    are read from ``_maker_image_state``.
    """
    def _update(*_):
        s = getattr(widget, "_maker_image_state", None)
        if s is None:
            return
        try:
            s[axis] = max(1, int(var.get()))
        except (TypeError, ValueError):
            return
        _rebuild_image_for_widget(widget)
    var.trace_add("write", _update)
    _update()


def _bind_var_to_preserve_aspect(var, widget):
    """Map ``var.get()`` (bool) to whether the image preserves its
    native aspect ratio inside (width, height) or stretches.
    """
    def _update(*_):
        s = getattr(widget, "_maker_image_state", None)
        if s is None:
            return
        s["aspect"] = bool(var.get())
        _rebuild_image_for_widget(widget)
    var.trace_add("write", _update)
    _update()
'''

# Phase 2c — ``font_autofit`` (CTkLabel) drives whether the font size
# is automatically chosen to fit the label's width/height. The
# rebuilder ports Maker's binary-search autofit algorithm to runtime
# so a toggle on a live label recomputes the best-fit size from the
# widget's current text + width + height (so resizes after
# construction still produce the right autofit). When the var
# flips back to False, the font's size is restored to the original
# captured at emit time.
_AUTO_TRACE_FONT_AUTOFIT_HELPER = '''def _bind_var_to_font_autofit(var, widget, size_off):
    """Map ``var.get()`` (bool) to CTkLabel font-size autofit.
    True → binary-search the largest font size that fits the
    widget's current text inside its current width/height (mirrors
    the editor's autofit). False → restore the original ``size_off``
    captured at construction.
    """
    import tkinter.font as _tkfont

    def _wrap_lines(font, text, max_w):
        lines = []
        for paragraph in str(text).split("\\n"):
            if not paragraph:
                lines.append("")
                continue
            cur = ""
            for word in paragraph.split(" "):
                trial = word if not cur else cur + " " + word
                if font.measure(trial) <= max_w:
                    cur = trial
                else:
                    if cur:
                        lines.append(cur)
                    cur = word
            if cur:
                lines.append(cur)
        return lines or [""]

    def _compute(text, width, height, bold, wrap):
        avail_w = max(10, int(width) - 12)
        avail_h = max(10, int(height) - 4)
        weight = "bold" if bold else "normal"
        lo, hi, best = 6, 96, 6
        while lo <= hi:
            mid = (lo + hi) // 2
            try:
                f = _tkfont.Font(size=mid, weight=weight)
                line_h = f.metrics("linespace")
                if wrap:
                    lns = _wrap_lines(f, text, avail_w)
                    tw = max((f.measure(L) for L in lns), default=0)
                    th = line_h * len(lns)
                else:
                    tw = f.measure(text)
                    th = line_h
            except Exception:
                return 13
            if tw <= avail_w and th <= avail_h:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def _rebuild_font(new_size):
        current = widget.cget("font")
        widget.configure(font=ctk.CTkFont(
            family=current.cget("family"),
            size=int(new_size),
            weight=current.cget("weight"),
            slant=current.cget("slant"),
            underline=current.cget("underline"),
            overstrike=current.cget("overstrike"),
        ))

    def _update(*_):
        if var.get():
            try:
                text = widget.cget("text") or ""
                width = int(widget.cget("width") or 100)
                height = int(widget.cget("height") or 28)
                current_font = widget.cget("font")
                bold = current_font.cget("weight") == "bold"
                wrap = int(widget.cget("wraplength") or 0) > 0
            except Exception:
                return
            _rebuild_font(_compute(text, width, height, bold, wrap))
        else:
            _rebuild_font(size_off)
    var.trace_add("write", _update)
    _update()
'''

_PACK_BALANCE_HELPER = '''def _ctkmaker_balance_pack(container, axis):
    """Flex-shrink pack children along ``axis`` ("width" or
    "height") when the container drops below the sum of their
    nominal sizes. Honors ``_ctkmaker_fixed=True`` (skip — keeps
    the user-locked size) and ``_ctkmaker_min`` (per-child content
    floor so text + icon never clip). Mirrors the canvas preview's
    hbox/vbox auto-shrink semantics so the exported app matches
    what the user sees in CTk Maker.

    All math runs in CTk's widget-scaling units, not raw pixels —
    ``configure(width=N)`` on a CTk widget multiplies N by the
    container's DPI scaling factor before resizing the underlying
    tk widget, so feeding raw winfo_width() in would over-allocate
    on hi-DPI displays (e.g. 1.5× scaling renders an 80-CTk-unit
    button at 120 raw px; mixing the two units leaves later
    siblings starved at 1 px).
    """
    children = container.pack_slaves()
    if not children:
        return
    # CTkScrollableFrame is itself the inner tk.Frame (its __init__
    # does ``tkinter.Frame.__init__(self, master=self._parent_canvas)``)
    # which auto-grows to fit children's natural size. Reading
    # ``container.winfo_*`` here returns that grown content size, so
    # flex math against it never shrinks anything (avail == content
    # total → slot == nominal width). Read from the outer
    # ``_parent_canvas`` instead so distribution targets the actual
    # viewport — that's what the user sees and what the canvas
    # preview already pivots on.
    size_source = getattr(container, "_parent_canvas", None) or container
    if axis == "width":
        raw_size = size_source.winfo_width()
        pad_key = "padx"
    else:
        raw_size = size_source.winfo_height()
        pad_key = "pady"
    if raw_size <= 1:
        return
    # CTk's window root (CTk / CTkToplevel) doesn't carry
    # ``_get_widget_scaling`` — only nested CTkBaseClass widgets do —
    # so ask the first scaling-aware child instead. Falls back to
    # 1.0 for pure-tk parents (no DPI awareness).
    scale = 1.0
    try:
        scale = float(container._get_widget_scaling())
    except (AttributeError, Exception):
        for c in children:
            try:
                scale = float(c._get_widget_scaling())
                break
            except (AttributeError, Exception):
                continue
    if scale <= 0:
        scale = 1.0
    container_size = int(raw_size / scale)
    spacing_total = 0
    fixed_total = 0
    grow_kids = []
    for c in children:
        try:
            info = c.pack_info()
        except Exception:
            continue
        pad = info.get(pad_key, 0)
        if isinstance(pad, tuple):
            spacing_raw = int(pad[0]) + int(pad[1])
        else:
            spacing_raw = int(pad) * 2
        spacing_total += int(spacing_raw / scale)
        if getattr(c, "_ctkmaker_fixed", False):
            try:
                fixed_total += int(c.cget(axis))
            except Exception:
                fixed_total += int(
                    (c.winfo_reqwidth() if axis == "width"
                     else c.winfo_reqheight()) / scale,
                )
        else:
            grow_kids.append(c)
    if not grow_kids:
        return
    avail = max(1, container_size - fixed_total - spacing_total)
    slot = max(1, avail // len(grow_kids))
    for c in grow_kids:
        floor = getattr(c, "_ctkmaker_min", 1)
        target = max(floor, slot)
        # Image (CTkLabel + CTkImage) needs the embedded CTkImage
        # resized explicitly — configuring the label alone leaves
        # the picture at its constructor-time size=(W, H).
        if getattr(c, "_ctkmaker_image", False):
            ctk_img = getattr(c, "_image", None)
            if ctk_img is not None:
                try:
                    cur_size = ctk_img.cget("size")
                    if axis == "width":
                        ctk_img.configure(size=(target, cur_size[1]))
                    else:
                        ctk_img.configure(size=(cur_size[0], target))
                except Exception:
                    pass
        try:
            c.configure(**{axis: target})
        except Exception:
            pass
'''
