from fastapi import APIRouter

from app.schemas.directory import CommonDirectoriesSchema
from app.services.directories_service import DirectoriesService

router = APIRouter()

directories_service = DirectoriesService()


@router.get("/common", response_model=CommonDirectoriesSchema)
def get_common_directories() -> CommonDirectoriesSchema:
    return directories_service.get_common_directories()
