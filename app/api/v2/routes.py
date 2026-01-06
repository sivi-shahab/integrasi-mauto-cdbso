from fastapi import APIRouter, Depends

from app.api.v1.endpoints import report_mauto_endpoints
from app.core.api_key_auth import validate_api_key

router = APIRouter(
    dependencies=[Depends(validate_api_key)]
)

router.include_router(
    report_mauto_endpoints.router,
    prefix="/report_mauto",
    tags=["Report Mauto CDSBO"]
)
