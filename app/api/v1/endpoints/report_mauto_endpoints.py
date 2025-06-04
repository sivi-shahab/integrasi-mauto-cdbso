from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.report_mauto_schema import ReportMautoCdsboResponse
from app.service.report_mauto_service import ReportMautoService
from app.core.deps import get_db
from typing import List


router = APIRouter()

@router.get("",
            response_model=List[ReportMautoCdsboResponse],
            summary="Get Report Mauto CDSBO",
            description="Retrieve report mauto cdsbo data based on apply date, nik, branch code, and account number."
)
def get_report_mauto(
    apply_date: str,
    nik: str = None,
    branch_code: str = None,
    account_number: str = None,
    db: Session = Depends(get_db)
) -> List[ReportMautoCdsboResponse]:
    """
    Get report mauto cdsbo data based on the provided filters.
    
    - **apply_date**: Date in ddmmyyyy format.
    - **nik**: Optional NIK filter.
    - **branch_code**: Optional branch code filter.
    - **account_number**: Optional account number filter.
    """
    try:
        return ReportMautoService.get_report_mauto(db, apply_date, nik, branch_code, account_number)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
