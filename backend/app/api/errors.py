"""Every error response uses {"error": {"code": "...", "message": "..."}}."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import AppError

logger = logging.getLogger(__name__)

STATUS_BY_CODE = {
    "not_found": 404,
    "invalid_transition": 409,
    "llm_error": 502,
}


def _envelope(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _envelope(STATUS_BY_CODE.get(exc.code, 500), exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0]  # message only: the echoed input is not returned
        where = ".".join(str(part) for part in first["loc"])
        return _envelope(422, "validation_error", f"{where}: {first['msg']}")

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error", exc_info=exc)
        return _envelope(500, "internal_error", "Internal server error")
