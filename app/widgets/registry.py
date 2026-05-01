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
from app.widgets.ctk_slider import CTkSliderDescriptor
from app.widgets.ctk_switch import CTkSwitchDescriptor
from app.widgets.ctk_tabview import CTkTabviewDescriptor
from app.widgets.ctk_textbox import CTkTextboxDescriptor
from app.widgets.card import CardDescriptor
from app.widgets.circular_progress import CircularProgressDescriptor
from app.widgets.image import ImageDescriptor
from app.widgets.window_descriptor import WindowDescriptor


_REGISTRY: dict[str, type[WidgetDescriptor]] = {
    WindowDescriptor.type_name: WindowDescriptor,
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
    CTkSliderDescriptor.type_name: CTkSliderDescriptor,
    CTkSwitchDescriptor.type_name: CTkSwitchDescriptor,
    CTkTabviewDescriptor.type_name: CTkTabviewDescriptor,
    CTkTextboxDescriptor.type_name: CTkTextboxDescriptor,
    ImageDescriptor.type_name: ImageDescriptor,
    CardDescriptor.type_name: CardDescriptor,
    CircularProgressDescriptor.type_name: CircularProgressDescriptor,
}


def get_descriptor(type_name: str) -> type[WidgetDescriptor] | None:
    return _REGISTRY.get(type_name)


def all_descriptors() -> list[type[WidgetDescriptor]]:
    return list(_REGISTRY.values())
