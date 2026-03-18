from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.core.security import TokenError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": str(exc), "data": None},
        )

    @app.exception_handler(TokenError)
    async def token_error_handler(_: Request, exc: TokenError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"code": "forbidden", "message": str(exc) or "invalid token", "data": None},
        )
