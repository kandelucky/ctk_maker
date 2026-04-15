from app.widgets.base import WidgetDescriptor
from app.widgets.ctk_button import CTkButtonDescriptor
from app.widgets.ctk_check_box import CTkCheckBoxDescriptor
from app.widgets.ctk_combo_box import CTkComboBoxDescriptor
from app.widgets.ctk_entry import CTkEntryDescriptor
from app.widgets.ctk_frame import CTkFrameDescriptor
from app.widgets.ctk_label import CTkLabelDescriptor
from app.widgets.ctk_option_menu import CTkOptionMenuDescriptor
from app.widgets.ctk_progress_bar import CTkProgressBarDescriptor
from app.widgets.ctk_radio_button import CTkRadioButtonDescriptor
from app.widgets.ctk_scrollable_frame import CTkScrollableFrameDescriptor
from app.widgets.ctk_segmented_button import CTkSegmentedButtonDescriptor


_REGISTRY: dict[str, type[WidgetDescriptor]] = {
    CTkButtonDescriptor.type_name: CTkButtonDescriptor,
    CTkCheckBoxDescriptor.type_name: CTkCheckBoxDescriptor,
    CTkComboBoxDescriptor.type_name: CTkComboBoxDescriptor,
    CTkEntryDescriptor.type_name: CTkEntryDescriptor,
    CTkLabelDescriptor.type_name: CTkLabelDescriptor,
    CTkFrameDescriptor.type_name: CTkFrameDescriptor,
    CTkOptionMenuDescriptor.type_name: CTkOptionMenuDescriptor,
    CTkProgressBarDescriptor.type_name: CTkProgressBarDescriptor,
    CTkRadioButtonDescriptor.type_name: CTkRadioButtonDescriptor,
    CTkScrollableFrameDescriptor.type_name: CTkScrollableFrameDescriptor,
    CTkSegmentedButtonDescriptor.type_name: CTkSegmentedButtonDescriptor,
}


def get_descriptor(type_name: str) -> type[WidgetDescriptor] | None:
    return _REGISTRY.get(type_name)


def all_descriptors() -> list[type[WidgetDescriptor]]:
    return list(_REGISTRY.values())
