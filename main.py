import logging

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routes import router as api_v1_router
from app.api.v2.routes import router as api_v2_router
from app.core.logging import setup_logging
from app.schemas.response import ResponseCode

logger = logging.getLogger(__name__)

def create_application() -> FastAPI:
    """API For Report Mauto CDSBO"""
    setup_logging()
    logger.info("Starting FastAPI application")

    application = FastAPI(
        title="Report Mauto CDSBO API",
        description="API for managing Report Mauto CDSBO",
        version="1.0.0"
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_v1_router, prefix="/v1")
    application.include_router(api_v2_router, prefix="/v2")

    logger.info("FastAPI application configured successfully")
    return application

app = create_application()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    error_messages = []

    for error in errors:
        if error["type"] == "value_error":
            error_messages.append(error["msg"])
        else:
            field = ".".join(str(loc) for loc in error["loc"][1:])
            error_messages.append(f"{field}: {error['msg']}")

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "responseCode": ResponseCode.BAD_REQUEST,
            "responseDescription": "; ".join(error_messages),
            "data": None
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    # Log the full error for debugging
    logger.error(f"Internal Server Error: {str(exc)}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "responseCode": ResponseCode.INTERNAL_ERROR,
            "responseDescription": "Internal Server Error",
            "data": None
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Map HTTP status code ke ResponseCode
    response_code_map = {
        400: ResponseCode.BAD_REQUEST,
        401: ResponseCode.UNAUTHORIZED,
        403: ResponseCode.FORBIDDEN,
        404: ResponseCode.NOT_FOUND,
        500: ResponseCode.INTERNAL_ERROR,
    }

    response_code = response_code_map.get(exc.status_code, ResponseCode.INTERNAL_ERROR)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "responseCode": response_code.value,
            "responseDescription": exc.detail,
            "data": None
        }
    )


if __name__ == "__main__":
    from app.core.configs import settings
    from app.db.session import check_connection_budget, pool_settings

    # Gagal start jika total koneksi melebihi budget (README k6 §9.2).
    total = check_connection_budget(settings.APP_WORKERS)
    logger.info(
        "Start %d worker, pool per worker %s, total koneksi DB maks %d (budget %d)",
        settings.APP_WORKERS, pool_settings(), total, settings.DB_CONNECTION_BUDGET,
    )
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        workers=settings.APP_WORKERS,
        reload=False,
    )
