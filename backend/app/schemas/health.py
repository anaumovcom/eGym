from app.schemas.base import SchemaModel


class HealthResponseSchema(SchemaModel):
    status: str
    environment: str
    database: str
    redis: str
    openapi_url: str
