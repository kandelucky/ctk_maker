"""CTkRadioButton widget descriptor.

A labeled radio button. Multiple radios that share a `variable`
form a group where only one can be selected at a time; in the
builder preview each radio is standalone and the grouping is
resolved during code export.

Groups shown in the Properties panel, in order
(Content → Layout → Visual → Behavior):

    Text               — label, font + style, text colors
    Geometry           — x/y, widget size
    Dot                — the dot's size, corner radius, border widths
    Main Colors        — fill (when checked), hover
    Button Interaction — interactable, hover, initial state
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkRadioButtonDescriptor(WidgetDescriptor):
    type_name = "CTkRadioButton"
    display_name = "Radio Button"

    default_properties = {
        # Geometry — small default so the widget auto-grows around
        # its content; otherwise the bg stays at the configured size
        # and looks misaligned when ``text_position`` moves the label.
        "x": 120,
        "y": 120,
        "width": 20,
        "height": 10,
        # Rectangle
        "corner_radius": 11,
        "border_width_unchecked": 3,
        "border_width_checked": 6,
        # Radio dot size
        "radiobutton_width": 22,
        "radiobutton_height": 22,
        # Button Interaction
        "button_enabled": True,
        "hover": True,
        "initially_checked": False,
        "group": "",
        # Main colors
        "fg_color": "#6366f1",
        "hover_color": "#4f46e5",
        # Text content + style
        "text": "CTkRadioButton",
        "font_family": None,
        "font_size": 13,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
        "text_color": "#dce4ee",
        "text_color_disabled": "#737373",
        "text_position": "right",
        "text_spacing": 6,
    }

    property_schema = [
        # --- Text --------------------------------------------------------
        {"name": "text", "type": "multiline", "label": "",
         "group": "Text", "row_label": "Label"},

        {"name": "font_family", "type": "font", "label": "",
         "group": "Text", "row_label": "Font"},

        {"name": "font_size", "type": "number", "label": "",
         "group": "Text", "row_label": "Size", "min": 6, "max": 96},

        {"name": "font_bold", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Bold"},
        {"name": "font_italic", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Italic"},
        {"name": "font_underline", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Underline"},
        {"name": "font_overstrike", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Strike"},

        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Normal Text Color"},
        {"name": "text_color_disabled", "type": "color", "label": "",
         "group": "Text", "row_label": "Disabled Text Color"},
        {"name": "text_position", "type": "text_position", "label": "",
         "group": "Text", "row_label": "Text Position"},
        {"name": "text_spacing", "type": "number", "label": "",
         "group": "Text", "row_label": "Text Spacing",
         "min": 0, "max": 100},

        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 20, "max": 2000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 10, "max": 2000},

        # --- Dot ---------------------------------------------------------
        {"name": "radiobutton_width", "type": "number", "label": "W",
         "group": "Dot", "pair": "box_size",
         "row_label": "Dot Size", "min": 10, "max": 200},
        {"name": "radiobutton_height", "type": "number", "label": "H",
         "group": "Dot", "pair": "box_size",
         "min": 10, "max": 200},

        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Dot",
         "row_label": "Corner Radius", "min": 0,
         "max": lambda p: max(
             0,
             min(int(p.get("radiobutton_width", 0)),
                 int(p.get("radiobutton_height", 0))) // 2,
         )},
        {"name": "border_width_unchecked", "type": "number", "label": "",
         "group": "Dot",
         "row_label": "Unchecked Width", "min": 0,
         "max": lambda p: max(
             1,
             min(int(p.get("radiobutton_width", 0)),
                 int(p.get("radiobutton_height", 0))) // 2,
         )},
        {"name": "border_width_checked", "type": "number", "label": "",
         "group": "Dot",
         "row_label": "Checked Width", "min": 0,
         "max": lambda p: max(
             1,
             min(int(p.get("radiobutton_width", 0)),
                 int(p.get("radiobutton_height", 0))) // 2,
         )},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Fill (Checked)"},
        {"name": "hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Hover",
         "disabled_when": lambda p: not p.get("hover")},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Hover Effect"},
        {"name": "initially_checked", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Initially Checked"},
        {"name": "group", "type": "multiline", "label": "",
         "group": "Button Interaction", "row_label": "Group"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y",
        "button_enabled", "initially_checked", "group",
        # builder-only — re-grids CTk's internal layout with a gap.
        "text_position", "text_spacing",
    }
    _FONT_KEYS = {
        "font_family",
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike",
    }

    # Changing the group name requires a fresh widget because variable
    # + value are init-only kwargs.
    recreate_triggers = frozenset({"group"})

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS and k not in cls._FONT_KEYS
        }

        result["state"] = (
            "normal" if properties.get("button_enabled", True)
            else "disabled"
        )

        try:
            size = int(properties.get("font_size") or 13)
        except (ValueError, TypeError):
            size = 13
        weight = "bold" if properties.get("font_bold") else "normal"
        slant = "italic" if properties.get("font_italic") else "roman"
        underline = bool(properties.get("font_underline"))
        overstrike = bool(properties.get("font_overstrike"))
        from app.core.fonts import resolve_effective_family
        family = resolve_effective_family(
            cls.type_name, properties.get("font_family"),
        )
        try:
            result["font"] = ctk.CTkFont(
                family=family,
                size=size, weight=weight, slant=slant,
                underline=underline, overstrike=overstrike,
            )
        except Exception:
            log_error("CTkRadioButtonDescriptor.transform_properties font")

        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        # `variable` + `value` come from the workspace via init_kwargs
        # when a group name is set — CTkRadioButton accepts them only
        # in __init__, not via `configure`.
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkRadioButton(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        # Group radios rely on the workspace syncing the shared
        # `tk.StringVar`; calling `.deselect()` here would clobber
        # another radio in the same group.
        in_group = bool(str(properties.get("group") or "").strip())
        try:
            if properties.get("initially_checked"):
                widget.select()
            elif not in_group:
                widget.deselect()
        except Exception:
            log_error("CTkRadioButtonDescriptor.apply_state")
        try:
            spacing = int(properties.get("text_spacing", 6) or 0)
        except (TypeError, ValueError):
            spacing = 6
        position = properties.get("text_position", "right") or "right"
        # Gate the re-grid: only run when position/spacing actually
        # change. Re-running grid_forget+grid on every property edit
        # disturbs CTk's internal cursor state on the inner canvas
        # and label, which the workspace selection chrome relies on.
        last_pos = getattr(widget, "_last_text_position", None)
        last_spacing = getattr(widget, "_last_text_spacing", None)
        if position == last_pos and spacing == last_spacing:
            return
        cls._reposition_text(widget, position, spacing)
        widget._last_text_position = position
        widget._last_text_spacing = spacing

    @classmethod
    def _reposition_text(
        cls, widget, position: str, spacing: int = 6,
    ) -> None:
        """Re-grid CTk's internal canvas + label so the label sits
        on the chosen side of the radio dot. Same shape and reach as
        the CheckBox version (CTk's CTkRadioButton ships with the
        same internal grid layout).
        """
        canvas = getattr(widget, "_canvas", None)
        label = getattr(widget, "_text_label", None)
        bg = getattr(widget, "_bg_canvas", None)
        if canvas is None or label is None:
            return
        spacing = max(0, int(spacing))
        # Snapshot the outer widget's cursor so we can re-apply it to
        # the inner canvas/label after the re-grid. The builder's
        # workspace sets cursor="fleur" on the outer widget for drag,
        # and CTk's internal _set_cursor on the inner widgets
        # otherwise reverts to "hand2" mid-edit.
        try:
            outer_cursor = str(widget.cget("cursor")) or ""
        except Exception:
            outer_cursor = ""
        try:
            canvas.grid_forget()
            label.grid_forget()
            if bg is not None:
                bg.grid_forget()
            if position == "left":
                if bg is not None:
                    bg.grid(row=0, column=0, columnspan=3, sticky="nswe")
                label.grid(row=0, column=0, sticky="e", padx=(0, spacing))
                canvas.grid(row=0, column=2, sticky="w")
                label["anchor"] = "e"
            elif position == "top":
                if bg is not None:
                    bg.grid(row=0, column=0, rowspan=3, columnspan=3, sticky="nswe")
                label.grid(row=0, column=0, sticky="s", pady=(0, spacing))
                canvas.grid(row=2, column=0, sticky="n")
                label["anchor"] = "center"
            elif position == "bottom":
                if bg is not None:
                    bg.grid(row=0, column=0, rowspan=3, columnspan=3, sticky="nswe")
                canvas.grid(row=0, column=0, sticky="s")
                label.grid(row=2, column=0, sticky="n", pady=(spacing, 0))
                label["anchor"] = "center"
            else:  # "right" — CTk default
                if bg is not None:
                    bg.grid(row=0, column=0, columnspan=3, sticky="nswe")
                canvas.grid(row=0, column=0, sticky="e")
                label.grid(row=0, column=2, sticky="w", padx=(spacing, 0))
                label["anchor"] = "w"
        except Exception:
            log_error("CTkRadioButtonDescriptor._reposition_text")
            return
        # Re-apply the outer widget's cursor to the inner widgets.
        # In the builder, ``outer_cursor == "fleur"`` (drag); in the
        # exported runtime it falls back to CTk's normal "hand2".
        propagate = outer_cursor or "hand2"
        for w in (canvas, label, bg):
            if w is None:
                continue
            try:
                w.configure(cursor=propagate)
            except Exception:
                pass

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        lines: list[str] = []
        # Group-coupled radios are primed via the shared StringVar
        # (the exporter emits a ``self._rg_<group>.set("rN")`` line
        # right after this widget's construction). Standalone radios
        # use the plain ``.select()`` path.
        if properties.get("initially_checked") and not str(
            properties.get("group") or "",
        ).strip():
            lines.append(f"{var_name}.select()")
        position = properties.get("text_position", "right") or "right"
        try:
            spacing = int(properties.get("text_spacing", 6) or 6)
        except (TypeError, ValueError):
            spacing = 6
        if position != "right" or spacing != 6:
            lines.append(
                f'_align_text_label({var_name}, "{position}", {spacing})'
            )
        return lines
