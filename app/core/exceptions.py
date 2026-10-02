import logging 
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse 

logger=logging.getLogger("quickcart.errors")

class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers

class BadRequestError(AppError):
    status_code,code=400,"bad_request"
    