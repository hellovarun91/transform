import uvicorn

from .config import load_settings


def main() -> None:
    settings = load_settings()
    from .app import create_app
    from .db import Store
    from .plan import load_plan

    store = Store(settings.db_path)
    plan = load_plan()
    app = create_app(settings, store=store, plan=plan, start_scheduler=True)
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
