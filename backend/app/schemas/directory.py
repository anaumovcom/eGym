from app.schemas.base import SchemaModel


class DirectoryItemSchema(SchemaModel):
    value: str
    label: str


class CommonDirectoriesSchema(SchemaModel):
    roles: list[DirectoryItemSchema]
    accents: list[DirectoryItemSchema]
    machine_states: list[DirectoryItemSchema]
    drive_states: list[DirectoryItemSchema]
    safety_states: list[DirectoryItemSchema]
