from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.routes import router as api_v1_router
from app.core.logging import setup_logging
import logging
import uvicorn
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import Request, status
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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8013, reload=False)
