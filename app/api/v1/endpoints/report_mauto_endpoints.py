from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.service.report_mauto_service import ReportMautoService
from app.core.deps import get_db
from app.schemas.report_mauto_schema import ReportMautoCdsboRequest, ReportMautoCdsboResponse
from app.schemas.response import error_response, ResponseCode
from logging import getLogger

logger = getLogger(__name__)


router = APIRouter()

@router.post("",
            summary="Get Report Mauto CDSBO",
            description="Retrieve report mauto cdsbo data based on apply date, nik, branch code, and account number."
)
def get_report_mauto(
    request: ReportMautoCdsboRequest,
    db: Session = Depends(get_db)
) -> ReportMautoCdsboResponse:
    """
    Get report mauto cdsbo data based on the provided filters.
    
    - **apply_date**: Date in ddmmyyyy format.
    - **nik**: Optional NIK filter.
    - **branch_code**: Optional branch code filter.
    - **account_number**: Optional account number filter.
    """
    try:
        if request.limit < 0 or request.offset < 0:
            return error_response(ResponseCode.BAD_REQUEST, "Limit and offset must be greater than or equal to 0")
        return ReportMautoService.get_report_mauto(db, request=request, limit=request.limit, offset=request.offset)
    except HTTPException as e:
        logger.error(f"HTTPException: {e}")
        raise e
    except Exception as e:
        logger.error(f"Exception: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
