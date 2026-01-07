from fastapi import APIRouter, Depends

from app.api.v1.endpoints import liveness_endpoints, report_mauto_endpoints
from app.core.api_key_auth import validate_api_key

router = APIRouter(
    dependencies=[Depends(validate_api_key)]
)

router.include_router(
    report_mauto_endpoints.router,
    prefix="/report_mauto",
    tags=["Report Mauto CDSBO"]
)

router.include_router(
    liveness_endpoints.router,
    prefix='/liveness',
    tags=["Liveness Data For CDSBO"]
)
