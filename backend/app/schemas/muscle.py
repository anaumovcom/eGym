from app.schemas.base import SchemaModel


class MuscleCardSchema(SchemaModel):
    name: str
    status: str
    score: int