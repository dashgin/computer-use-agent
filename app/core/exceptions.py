"""
Exception handlers for the FastAPI application.
"""

import uuid

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.models.schemas import ErrorResponse, ValidationErrorResponse

logger = get_logger(__name__)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with structured error responses."""
    request_id = str(uuid.uuid4())

    # Convert validation errors to our format
    validation_errors = [
        {"field": ".".join(str(loc) for loc in error["loc"]), "message": error["msg"]}
        for error in exc.errors()
    ]

    error_response = ValidationErrorResponse(
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        validation_errors=validation_errors,
        request_id=request_id,
    )

    logger.warning(f"Validation error [{request_id}]: {exc}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.model_dump(mode="json"),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with structured error responses."""
    request_id = str(uuid.uuid4())

    error_response = ErrorResponse(
        error_code=f"HTTP_{exc.status_code}", message=exc.detail, request_id=request_id
    )

    logger.warning(f"HTTP exception [{request_id}]: {exc.status_code} - {exc.detail}")

    return JSONResponse(
        status_code=exc.status_code, content=error_response.model_dump(mode="json")
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    request_id = str(uuid.uuid4())

    error_response = ErrorResponse(
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
        details={"exception_type": type(exc).__name__},
        request_id=request_id,
    )

    logger.error(f"Unexpected exception [{request_id}]: {exc}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(mode="json"),
    )


def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app."""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler) 