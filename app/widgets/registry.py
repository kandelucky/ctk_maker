from app.widgets.base import WidgetDescriptor
from app.widgets.ctk_button import CTkButtonDescriptor
from app.widgets.ctk_frame import CTkFrameDescriptor
from app.widgets.ctk_label import CTkLabelDescriptor


_REGISTRY: dict[str, type[WidgetDescriptor]] = {
    CTkButtonDescriptor.type_name: CTkButtonDescriptor,
    CTkLabelDescriptor.type_name: CTkLabelDescriptor,
    CTkFrameDescriptor.type_name: CTkFrameDescriptor,
}


def get_descriptor(type_name: str) -> type[WidgetDescriptor] | None:
    return _REGISTRY.get(type_name)


def all_descriptors() -> list[type[WidgetDescriptor]]:
    return list(_REGISTRY.values())
