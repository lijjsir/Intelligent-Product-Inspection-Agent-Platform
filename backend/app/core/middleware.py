import uuid
import re
from fastapi import FastAPI, Request, Response

from app.core.config import settings


def register_middleware(app: FastAPI) -> None:
    allowed_origin_regex = (
        re.compile(settings.cors_allow_origin_regex)
        if settings.cors_allow_origin_regex
        else None
    )

    def resolve_cors_origin(origin: str | None) -> str | None:
        if not origin:
            return None
        if origin in settings.cors_allowed_origins:
            return origin
        if allowed_origin_regex and allowed_origin_regex.match(origin):
            return origin
        return None

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.org_id = request.headers.get("X-Org-Id")
        cors_origin = resolve_cors_origin(request.headers.get("origin"))

        if request.method == "OPTIONS" and cors_origin:
            response = Response(status_code=200)
        else:
            response = await call_next(request)

        response.headers["X-Request-Id"] = request_id
        if cors_origin:
            requested_headers = request.headers.get("access-control-request-headers") or "*"
            response.headers["Access-Control-Allow-Origin"] = cors_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "*"
            response.headers["Access-Control-Allow-Headers"] = requested_headers
            response.headers["Access-Control-Expose-Headers"] = "X-Request-Id"
            response.headers["Vary"] = "Origin"
        return response
