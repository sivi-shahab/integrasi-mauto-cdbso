from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.routes import router as api_v1_router
from app.core.logging import setup_logging
import logging
import uvicorn

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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
