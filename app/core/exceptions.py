import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("quickcart.errors")


class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers


class BadRequestError(AppError):
    status_code, code = 400, "bad_request"


class UnauthorizedError(AppError):
    status_code, code = 401, "unauthorized"

    def __init__(self, message: str = "Not authenticated") -> None:
        # RFC 6750: a 401 from a bearer-protected API must say which scheme to use
        super().__init__(message, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenError(AppError):
    status_code, code = 403, "forbidden"


class NotFoundError(AppError):
    status_code, code = 404, "not_found"


class ConflictError(AppError):
    status_code, code = 409, "conflict"


class PayloadTooLargeError(AppError):
    status_code, code = 413, "payload_too_large"


class UnsupportedMediaTypeError(AppError):
    status_code, code = 415, "unsupported_media_type"


class TooManyRequestsError(AppError):
    status_code, code = 429, "too_many_requests"


def register_exception_handlers(app: FastAPI) -> None:
    """Turn exceptions into one consistent JSON error shape."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback for us; show the client nothing internal.
        logger.exception(
            "unhandled_error", extra={"method": request.method, "path": request.url.path}
        )
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error"}},
        )
