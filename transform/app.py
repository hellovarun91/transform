from __future__ import annotations

from fastapi import FastAPI

from .config import Settings


def create_app(settings: Settings, store=None, plan=None, start_scheduler: bool = False) -> FastAPI:
    app = FastAPI(title="Transform", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.store = store
    app.state.plan = plan

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
