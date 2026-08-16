from fastapi import APIRouter

from .files_controller import router as files_router
from .health_controller import router as health_router
from .image_generation_controller import router as generation_router


api_router = APIRouter()
api_router.include_router(files_router)
api_router.include_router(health_router)
api_router.include_router(generation_router)
