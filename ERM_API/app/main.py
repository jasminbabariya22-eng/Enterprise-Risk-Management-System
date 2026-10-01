from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
# from app.models.user import User
from app.api.auth import router as auth_router
from app.api.user import router as user_router
#from app.schemas.user import UserResponse
from typing import List

# Import logging
from fastapi import Request
from app.core.logger import logger
import time
# import json
from starlette.responses import Response
from fastapi.responses import JSONResponse

from app.api.department import router as dept_router
from app.api.role import router as role_router
from app.api.user_type import router as user_type_router

from app.api.risk_register import router as risk_registery_router
from app.api.risk_description import router as risk_description_router
from app.api.risk_treatment import router as risk_treatment_router

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.exception_handler import (
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)

from app.api.Status import router as status_router
from app.api.risk_api import router as risk_router

from app.api.risk_action_followup import router as risk_action_followup_router
from app.api.approval import router as approval_router

from app.api.risk_dashboard_api import router as risk_dashboard_router

from app.api.user_role_map import router as user_role_map_router
from app.api.menu_mst import router as menu_map_router

from app.api.email_job_api import router as email_job_router

from app.api.financial_year import router as financial_year_router
from dotenv import load_dotenv
import os

from app.api.excel_import_router import router as excel_import_router

load_dotenv()

app = FastAPI()


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "service": "ESM API"
    }

# Authenticate and get current user
app.include_router(auth_router)

# Include Master Data APIs
app.include_router(user_router)
app.include_router(dept_router)
app.include_router(role_router)
app.include_router(user_type_router)

# Full Risk Register APIs
app.include_router(risk_router)

# Dashboard
app.include_router(risk_dashboard_router)

# Menu and role_map
app.include_router(menu_map_router)
app.include_router(user_role_map_router)

# Email Job API
app.include_router(email_job_router)

# Approval and Status APIs
app.include_router(status_router)
app.include_router(risk_action_followup_router)
app.include_router(approval_router)

# Risk Register APIs
app.include_router(risk_registery_router)
app.include_router(risk_description_router)
app.include_router(risk_treatment_router)

# Financial Year API
app.include_router(financial_year_router)

# Excel Import API
app.include_router(excel_import_router)

# Add global exception handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


## Logging Middleware
## Ultra-Fast Non-Blocking Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({process_time:.3f}s)")
    return response

# @app.exception_handler(Exception)
# async def global_exception_handler(request: Request, exc: Exception):
#     logger.error(
#         f"ERROR | {request.method} {request.url} | MESSAGE: {str(exc)}"
#     )
#     return JSONResponse(
#         status_code=500,
#         content={"detail": "Internal Server Error"}
#     )