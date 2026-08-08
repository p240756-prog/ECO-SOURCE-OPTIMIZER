from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class EcoSourceOptimizerError(Exception):
    """
    Base exception for known application errors.
    """

    status_code = 500
    error_code = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationError(EcoSourceOptimizerError):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class ResourceNotFoundError(EcoSourceOptimizerError):
    status_code = 404
    error_code = "RESOURCE_NOT_FOUND"


class DecisionError(EcoSourceOptimizerError):
    status_code = 422
    error_code = "DECISION_ERROR"


class SafetyViolationError(EcoSourceOptimizerError):
    status_code = 409
    error_code = "SAFETY_VIOLATION"


async def ecosource_optimizer_exception_handler(
    request: Request,
    exc: EcoSourceOptimizerError,
) -> JSONResponse:
    """
    Converts known application exceptions into a consistent API response.
    """

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Prevents internal exception details from leaking through the API.
    """

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected internal error occurred.",
                "details": None,
            }
        },
    )


def register_exception_handlers(app) -> None:
    """
    Registers EcoSourceOptimizer exception handlers with FastAPI.
    """

    app.add_exception_handler(
        EcoSourceOptimizerError,
        ecosource_optimizer_exception_handler,
    )

    app.add_exception_handler(
        Exception,
        unexpected_exception_handler,
    )