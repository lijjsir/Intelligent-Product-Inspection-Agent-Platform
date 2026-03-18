import uuid
from fastapi import FastAPI, Request


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.org_id = request.headers.get("X-Org-Id")
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
