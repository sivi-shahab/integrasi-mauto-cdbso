from sqlalchemy.orm import Session
from fastapi import status
from datetime import datetime
from typing import Optional
from fastapi.responses import JSONResponse

from sqlalchemy import cast, Date

from app.models.report_mauto_model import ReportMautoCdsbo
from app.schemas.report_mauto_schema import ReportMautoCdsboResponse, ReportMautoCdsboBase

class ReportMautoService:
    @staticmethod
    def get_report_mauto(
        db: Session,
        apply_date: str,
        nik: Optional[str] = None,
        branch_code: Optional[str] = None,
        account_number: Optional[str] = None
    ) -> ReportMautoCdsboResponse:
        try:
            try:
                parsed_date = datetime.strptime(apply_date, "%d%m%Y").date()
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "resposeCode": "01",
                        "responseDescription": "Invalid date format. Use ddmmyyyy.",
                        "data": None
                    }
                )

            query = db.query(ReportMautoCdsbo).filter(
                cast(ReportMautoCdsbo.apply_date, Date) == parsed_date
            )

            if nik:
                query = query.filter(ReportMautoCdsbo.nik == nik)
            if branch_code:
                query = query.filter(ReportMautoCdsbo.source_code == branch_code)
            if account_number:
                query = query.filter(ReportMautoCdsbo.account_number == account_number)

            results = query.all()
            return  JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "resposeCode": "00",
                    "responseDescription": "Success",
                    "data": [ReportMautoCdsboBase.model_validate(record).model_dump(mode='json',by_alias=True) for record in results]
                }
            )

        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "resposeCode": "99",
                    "responseDescription": f"An error occurred while fetching report mauto data: {str(e)}",
                    "data": None
                }
            )