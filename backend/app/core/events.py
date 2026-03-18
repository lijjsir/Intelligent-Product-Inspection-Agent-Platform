from fastapi import FastAPI

from app.core.logging import configure_logging


def register_events(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _startup() -> None:
        configure_logging()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        return None
