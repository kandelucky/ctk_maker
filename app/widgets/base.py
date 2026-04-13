class WidgetDescriptor:
    type_name: str = ""
    display_name: str = ""
    default_properties: dict = {}
    property_schema: list[dict] = []

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        return dict(properties)

    @classmethod
    def create_widget(cls, master, properties: dict):
        raise NotImplementedError
