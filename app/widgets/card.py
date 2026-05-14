"""Card widget descriptor.

A decoration element for backgrounds + content surfaces — rectangle /
rounded rectangle / circle (or pill, when width != height) with an
optional embedded image. Exports as a ``CTkFrame`` so the generated
code stays on CTk's public API, but the builder treats it as a leaf:
no children can be dropped inside, no layout manager rows on its
property panel.

Renamed from ``Shape`` (2026-04-27) — ``Card`` better captures the
widget's role as a Material/Bootstrap-style decoration container with
optional image content rather than a pure geometric shape. The
internal property ``shape_type`` still names the outline form
(rectangle / rounded / circle) — that's a property of the card, not
the widget identity.

``shape_type`` drives ``corner_radius`` derivation:
    - ``rectangle`` → 0 (locked)
    - ``rounded``   → user-picked, slider 0..min(W,H)/2
    - ``circle``    → min(W,H)/2 (locked, auto-pill on non-square)

Optional embedded image: a CTkLabel(text="", image=...) is placed
inside the frame at a 9-point anchor (nw / n / ne / w / center / e /
sw / s / se) with a small padding offset from the chosen edge. The
inner label is stashed on the frame as ``_card_image_label`` so
property updates can re-target it without recreating the outer frame.

Default fill is a neutral light gray so a fresh drop is visually
distinct from CTkFrame's neutral ``#2b2b2b`` panel — the user can
spot at a glance whether a block is a real container or a Card.
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor

SHAPE_RECTANGLE = "rectangle"
SHAPE_ROUNDED = "rounded"
SHAPE_CIRCLE = "circle"

DEFAULT_FG_COLOR = "#a2a2a2"

# 9-point anchor → (relx, rely) for tk place(). x/y offset is then
# applied per-edge so padding pushes toward the centre of the card.
_ANCHOR_REL = {
    "nw": (0.0, 0.0), "n": (0.5, 0.0), "ne": (1.0, 0.0),
    "w":  (0.0, 0.5), "center": (0.5, 0.5), "e":  (1.0, 0.5),
    "sw": (0.0, 1.0), "s": (0.5, 1.0), "se": (1.0, 1.0),
}


class CardDescriptor(WidgetDescriptor):
    type_name = "Card"
    ctk_class_name = "CTkFrame"
    display_name = "Card"
    is_container = False
    prefers_fill_in_layout = True
    # The image is rendered by an inner CTkLabel that ``export_state``
    # emits AFTER the outer CTkFrame is built — CTkFrame itself
    # doesn't accept ``image=`` / ``compound=``, so the exporter must
    # skip the standard image-kwarg auto-emission.
    image_inline_kwarg = False

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 200,
        "height": 200,
        # Shape
        "shape_type": SHAPE_ROUNDED,
        "corner_radius": 12,
        # Border
        "border_enabled": False,
        "border_width": 1,
        "border_color": "#565b5e",
        # Main colors
        "fg_color": DEFAULT_FG_COLOR,
        # Image (optional embedded decoration)
        "image": None,
        "image_anchor": "center",
        "image_width": 48,
        "image_height": 48,
        "image_preserve_aspect": True,
        "image_pad_x": 0,
        "image_pad_y": 0,
        "image_color": None,
    }

    property_schema = [
        # --- Image -------------------------------------------------------
        {"name": "image", "type": "image", "label": "",
         "group": "Image", "row_label": "File"},
        {"name": "image_color", "type": "color", "label": "",
         "group": "Image", "row_label": "Tint",
         "clearable": True, "clear_value": "transparent",
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_anchor", "type": "anchor", "label": "",
         "group": "Image", "row_label": "Alignment",
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_width", "type": "number", "label": "W",
         "group": "Image", "pair": "image_size", "row_label": "Size",
         "min": 4, "max": 4000,
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_height", "type": "number", "label": "H",
         "group": "Image", "pair": "image_size",
         "min": 4, "max": 4000,
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_preserve_aspect", "type": "boolean", "label": "",
         "group": "Image", "row_label": "Preserve Aspect",
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_pad_x", "type": "number", "label": "X",
         "group": "Image", "pair": "image_pad", "row_label": "Padding",
         "min": lambda p: -int(p.get("width", 0) or 0),
         "max": lambda p: int(p.get("width", 0) or 0),
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_pad_y", "type": "number", "label": "Y",
         "group": "Image", "pair": "image_pad",
         "min": lambda p: -int(p.get("height", 0) or 0),
         "max": lambda p: int(p.get("height", 0) or 0),
         "disabled_when": lambda p: not p.get("image")},

        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 8, "max": 4000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 8, "max": 4000},

        # --- Shape -------------------------------------------------------
        {"name": "shape_type", "type": "enum", "label": "",
         "group": "Shape", "row_label": "Type",
         "options": [
             {"value": SHAPE_RECTANGLE, "label": "Rectangle",
              "icon": "square"},
             {"value": SHAPE_ROUNDED, "label": "Rounded",
              "icon": "square-round-corner"},
             {"value": SHAPE_CIRCLE, "label": "Circle / Pill",
              "icon": "circle"},
         ]},
        # corner_radius is editable only for "rounded" — rectangle locks
        # it to 0, circle locks it to min(W,H)/2.
        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Shape",
         "row_label": "Corner Radius", "min": 0,
         "max": lambda p: max(
             0,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         ),
         "disabled_when": lambda p: p.get("shape_type") != SHAPE_ROUNDED},

        # --- Border ------------------------------------------------------
        {"name": "border_enabled", "type": "boolean", "label": "",
         "group": "Border", "row_label": "Enabled"},
        {"name": "border_width", "type": "number", "label": "",
         "group": "Border", "row_label": "Thickness", "min": 1,
         "max": lambda p: max(
             1,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         ),
         "disabled_when": lambda p: not p.get("border_enabled")},
        {"name": "border_color", "type": "color", "label": "",
         "group": "Border", "row_label": "Color",
         "disabled_when": lambda p: not p.get("border_enabled")},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Fill",
         "clearable": True, "clear_value": "transparent"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y", "shape_type", "border_enabled",
        # Image rows are kept in the node for property panel display +
        # save/load, but the outer CTkFrame doesn't accept them as
        # constructor kwargs — apply_state builds an inner CTkLabel
        # using these values instead.
        "image", "image_anchor",
        "image_width", "image_height",
        "image_pad_x", "image_pad_y",
        "image_color", "image_preserve_aspect",
    }

    derived_triggers = {
        "shape_type", "width", "height",
    }

    @classmethod
    def compute_derived(cls, properties: dict) -> dict:
        # Lock corner_radius to the shape mode. Image aspect is now
        # handled at render time inside ``_sync_image_label`` (and the
        # exporter mirrors it) so the icon can contain-fit the image
        # without touching the stored ``image_height``.
        out: dict = {}
        shape = properties.get("shape_type", SHAPE_ROUNDED)
        try:
            w = int(properties.get("width", 0))
            h = int(properties.get("height", 0))
        except (TypeError, ValueError):
            w = h = 0
        if shape == SHAPE_RECTANGLE:
            if int(properties.get("corner_radius", 0) or 0) != 0:
                out["corner_radius"] = 0
        elif shape == SHAPE_CIRCLE:
            target = max(0, min(w, h) // 2)
            if int(properties.get("corner_radius", -1) or -1) != target:
                out["corner_radius"] = target
        return out

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
        }
        # Border off → zero out the width so CTk doesn't paint a hairline.
        if not properties.get("border_enabled"):
            result["border_width"] = 0
        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        frame = ctk.CTkFrame(master, **kwargs)
        cls._sync_image_label(frame, properties)
        return frame

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        """Emit lines for the inner ``CTkLabel`` that hosts the
        embedded image. The outer ``CTkFrame`` was already constructed
        + placed by the standard exporter path; these lines run after.
        Skipped when no image is set on the Card.
        """
        image_path = properties.get("image")
        if not image_path:
            return []
        # Convert in-assets absolute path to ``assets/<rel>`` so the
        # exported file resolves the asset via the sibling assets/
        # folder. Falls back to forward-slash absolute when the path
        # sits outside the project's assets/ tree.
        from app.io.code_exporter import _path_for_export
        normalised = _path_for_export(image_path)
        path_lit = repr(normalised)
        try:
            iw = max(4, int(properties.get("image_width", 48) or 48))
            ih = max(4, int(properties.get("image_height", 48) or 48))
        except (TypeError, ValueError):
            iw = ih = 48
        # Native contain-fit + tint (fork >= 5.4.4): CTkImage's
        # preserve_aspect scales the icon inside the (image_width,
        # image_height) box and the CTkLabel's image_color recolours
        # it — the exported code carries the raw box size + flags, no
        # emit-time PIL math.
        aspect = bool(properties.get("image_preserve_aspect"))
        tint = properties.get("image_color")
        tint = tint if tint and tint != "transparent" else None
        anchor = properties.get("image_anchor") or "center"
        relx, rely = _ANCHOR_REL.get(anchor, (0.5, 0.5))
        try:
            padx = int(properties.get("image_pad_x", 0) or 0)
            pady = int(properties.get("image_pad_y", 0) or 0)
        except (TypeError, ValueError):
            padx = pady = 0
        x_off = padx if "w" in anchor else (-padx if "e" in anchor else 0)
        y_off = pady if "n" in anchor else (-pady if "s" in anchor else 0)
        # ``var_name`` is the already-prefixed attribute reference
        # (e.g. ``self.card_1`` for a top-level node, or
        # ``self.frame_1.tab('Tab 1')`` inside a Tabview). Build the
        # inner-label attribute name by appending ``_image`` to it.
        img_attr = f"{var_name}_image"
        out_lines: list[str] = []
        out_lines.append(
            f"_card_src = Image.open({path_lit}).convert('RGBA')",
        )
        out_lines.append(
            f"{img_attr} = ctk.CTkLabel(",
        )
        out_lines.append(
            f"    {var_name}, text='', fg_color='transparent',",
        )
        out_lines.append(
            f"    image=ctk.CTkImage(light_image=_card_src, "
            f"dark_image=_card_src, size=({iw}, {ih}), "
            f"preserve_aspect={aspect}),",
        )
        if tint is not None:
            out_lines.append(f"    image_color={tint!r},")
        out_lines.append(")")
        out_lines.append(
            f"{img_attr}.place(relx={relx}, rely={rely}, "
            f"anchor={anchor!r}, x={x_off}, y={y_off})",
        )
        return out_lines

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        # Re-sync the inner image label whenever a property changes.
        # apply_state is the catch-all hook called after every commit
        # (and right after create_widget), so image swaps + anchor
        # tweaks land here without a full widget recreate.
        cls._sync_image_label(widget, properties)

    @classmethod
    def _sync_image_label(cls, frame, properties: dict) -> None:
        """Keep the embedded ``CTkLabel`` (text="", image=...) in sync
        with the Card's image properties. Creates / updates / removes
        the label as the user toggles ``image`` on and off.
        """
        image_path = properties.get("image")
        existing = getattr(frame, "_card_image_label", None)
        if not image_path:
            if existing is not None:
                try:
                    existing.destroy()
                except Exception:
                    pass
                frame._card_image_label = None
            return
        try:
            from PIL import Image as PILImage
            img = PILImage.open(image_path)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            iw = max(4, int(properties.get("image_width", 48) or 48))
            ih = max(4, int(properties.get("image_height", 48) or 48))
            # Native contain-fit + tint (fork >= 5.4.4): CTkImage's
            # preserve_aspect scales the icon inside (iw, ih) and the
            # CTkLabel's image_color recolours it — no PIL math here.
            ctk_img = ctk.CTkImage(
                light_image=img, dark_image=img, size=(iw, ih),
                preserve_aspect=bool(
                    properties.get("image_preserve_aspect")
                ),
            )
        except Exception:
            log_error("CardDescriptor._sync_image_label open")
            return
        tint = properties.get("image_color")
        tint = tint if tint and tint != "transparent" else None
        label = existing
        if label is None:
            label = ctk.CTkLabel(frame, text="", fg_color="transparent")
            frame._card_image_label = label
        try:
            label.configure(image=ctk_img, image_color=tint)
            # Hold a ref on the label so PIL+Tk don't garbage-collect
            # the underlying PhotoImage and blank the icon out.
            label.image = ctk_img  # type: ignore[attr-defined]
        except Exception:
            log_error("CardDescriptor._sync_image_label configure")
            return
        anchor = properties.get("image_anchor") or "center"
        relx, rely = _ANCHOR_REL.get(anchor, (0.5, 0.5))
        try:
            padx = int(properties.get("image_pad_x", 0) or 0)
            pady = int(properties.get("image_pad_y", 0) or 0)
        except (TypeError, ValueError):
            padx = pady = 0
        # Edge-aware padding: anchor-N pushes the label DOWN from the
        # top edge, anchor-S pushes UP from the bottom edge, etc.
        x_off = padx if "w" in anchor else (-padx if "e" in anchor else 0)
        y_off = pady if "n" in anchor else (-pady if "s" in anchor else 0)
        try:
            label.place(
                relx=relx, rely=rely, anchor=anchor,
                x=x_off, y=y_off,
            )
        except Exception:
            log_error("CardDescriptor._sync_image_label place")
