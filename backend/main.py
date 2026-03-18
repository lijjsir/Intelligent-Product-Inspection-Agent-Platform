from fastapi import FastAPI

from app.core.error_handlers import register_error_handlers
from app.core.events import register_events
from app.core.middleware import register_middleware
from app.api.v1.router import router as v1_router


def create_app() -> FastAPI:
    app = FastAPI(title="PIAP Backend", version="0.1.0")
    register_middleware(app)
    register_events(app)
    register_error_handlers(app)
    app.include_router(v1_router, prefix="/api/v1")

    @app.get("/")
    async def root():
        return {"message": "PIAP Backend is running successfully!", "docs": "/docs"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
