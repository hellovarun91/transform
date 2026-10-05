from fastapi import APIRouter

from .routes_auth import router as auth_router
from .routes_day import router as day_router
from .routes_meta import protected as meta_protected
from .routes_meta import router as meta_public

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(day_router)
api_router.include_router(meta_public)
api_router.include_router(meta_protected)
