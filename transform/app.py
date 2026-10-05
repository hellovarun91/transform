from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def create_app(settings: Settings, store=None, plan=None, start_scheduler: bool = False) -> FastAPI:
    app = FastAPI(title="Transform", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.store = store
    app.state.plan = plan
    from .auth import RateLimiter
    app.state.limiter = RateLimiter()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    from .api import api_router
    app.include_router(api_router)

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js")
    def sw():
        return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript",
                            headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def _no_cache_static(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"  # ETag revalidation; deploys never serve stale JS
        return response

    if start_scheduler and store is not None and plan is not None:
        from .scheduler import build_scheduler
        app.state.scheduler = build_scheduler(store, plan, settings)
        app.state.scheduler.start()

    return app
