from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.core.security import TokenError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        trace_id = exc.trace_id or request.headers.get("X-Trace-Id")
        error = exc.to_error()
        error["trace_id"] = trace_id
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "code": exc.code,
                "message": exc.message,
                "data": None,
                "error": error,
            },
        )

    @app.exception_handler(TokenError)
    async def token_error_handler(_: Request, exc: TokenError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "code": "forbidden",
                "message": str(exc) or "invalid token",
                "data": None,
                "error": {
                    "code": "forbidden",
                    "message": str(exc) or "invalid token",
                    "detail": None,
                    "module": "auth",
                    "trace_id": None,
                    "suggestion": None,
                },
            },
        )
