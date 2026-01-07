from logging import getLogger

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.liveness_schema import LivenessRequest
from app.schemas.response import ResponseCode, error_response
from app.service.liveness_service import LivenessService

logger = getLogger(__name__)


router = APIRouter()

@router.post("",
            summary="Get Liveness Data",
            description="Retrieve liveness data based on token."
)
def get_report_mauto(
    request: LivenessRequest,
    db: Session = Depends(get_db)
):
    """
    Get report mauto cdsbo data based on the provided filters.

    - **token**: token (string).
    """
    try:
        return LivenessService.get_liveness_data(db, request=request)
    except HTTPException as e:
        logger.error(f"HTTPException: {e}")
        raise e
    except Exception as e:
        logger.error(f"Exception: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
