from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logger import logger


# Custom exception handlers for FastAPI application
def build_error_response(status_code: int, message: str, details=None):
    return JSONResponse(
        status_code=status_code,
        content={
            "data": None,
            "Error": {
                "Success": False,
                "Error_message": message,
                "Code": status_code
            }
        },
    )

# HTTPException handler
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return build_error_response(exc.status_code, exc.detail)


# Validation error handler
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return build_error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Validation Error"
    )
    
    
# Generic exception handler for unhandled exceptions
async def generic_exception_handler(request: Request, exc: Exception):

    logger.exception(
        f"Unhandled Exception | {request.method} {request.url.path}"
    )

    return build_error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Internal Server Error"
    )

# # Generic exception handler for unhandled exceptions
# async def generic_exception_handler(request: Request, exc: Exception):
#     return build_error_response(
#         status.HTTP_500_INTERNAL_SERVER_ERROR,
#         "Internal Server Error"
#     )