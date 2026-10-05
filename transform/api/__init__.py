from fastapi import APIRouter

from .routes_auth import router as auth_router
from .routes_day import router as day_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(day_router)
