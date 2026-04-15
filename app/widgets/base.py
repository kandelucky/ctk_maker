class WidgetDescriptor:
    type_name: str = ""
    # Name of the actual CTk class the exporter should emit. Defaults
    # to type_name for descriptors that map 1:1 onto a CTk class
    # (CTkButton / CTkLabel / …). Builder-only composite widgets
    # (e.g. Image → CTkLabel with text="" + image=) override this.
    ctk_class_name: str = ""
    display_name: str = ""
    default_properties: dict = {}
    property_schema: list[dict] = []
    is_container: bool = False
    # Property keys that are stored as newline-separated strings in the
    # editor (multiline text box) but must be passed to CTk as a list of
    # strings at runtime. The exporter splits these on "\n" when emitting
    # the Python source so `CTkComboBox(values=...)` etc. gets a real
    # list, not a string CTk would iterate char-by-char.
    multiline_list_keys: set[str] = set()
    # Property keys that CTk accepts only in `__init__` — calling
    # `widget.configure(**{key: ...})` at runtime would raise. The editor
    # therefore filters these out of the configure kwargs and reinjects
    # them when creating the widget; any runtime change triggers a full
    # destroy + recreate via `recreate_triggers`. The exporter DOES emit
    # them because exported code builds the widget via `__init__`.
    init_only_keys: set[str] = set()

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        return dict(properties)

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        """Build the real CTk widget. `init_kwargs` holds extra
        constructor kwargs the workspace injects at creation time
        (e.g. a shared `tk.IntVar` + `value` for a radio button
        group) — they're merged on top of `transform_properties`.
        """
        raise NotImplementedError

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        """Runtime state that can't go through `configure(**kwargs)`.

        Called both after `create_widget` and after every property
        change. Default is a no-op; descriptors override when they
        need to call widget methods like `.select()` / `.deselect()`
        or push a slider value.
        """

    @classmethod
    def on_prop_recreate(cls, prop_name: str, properties: dict) -> dict:
        """Hook before the workspace destroys and recreates this widget
        in response to a `recreate_triggers` change. Returns a dict of
        properties to commit on the node before recreation (e.g. swap
        width/height when flipping a progress bar's orientation).
        Default is a no-op.
        """
        return {}

    @classmethod
    def canvas_anchor(cls, widget):
        """Return the widget the workspace should hand to
        `canvas.create_window` / `widget.place()`. For most widgets
        this is the widget itself, but composite widgets like
        CTkScrollableFrame — which wrap the user-visible frame inside
        an outer CTkFrame — must return the outer container so the
        canvas can embed them correctly. Children are still nested
        into the original `widget`.
        """
        return widget

    @classmethod
    def export_kwarg_overrides(cls, properties: dict) -> dict:
        """Per-descriptor kwarg transformations the exporter should
        apply when emitting the constructor call. Values returned here
        REPLACE the raw value from `node.properties`. Use this for
        runtime-only translations like CTkSlider's
        `number_of_steps=0 → None`. Default: no overrides.
        """
        return {}

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        """Lines the exporter should emit AFTER the widget has been
        constructed and placed. Used for runtime state that isn't a
        constructor kwarg — `.set(value)` / `.select()` /
        `.insert(0, text)` — mirroring `apply_state`. Default: none.
        """
        return []
