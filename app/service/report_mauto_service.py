from sqlalchemy.orm import Session
from fastapi import status
from datetime import datetime
from typing import Optional
from fastapi.responses import JSONResponse
from sqlalchemy import cast, Date, text, bindparam
from fastapi.encoders import jsonable_encoder
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
    ):
        try:
            # Parse apply_date with expected format
            try:
                parsed_date = datetime.strptime(apply_date, "%d%m%Y").date()
                parsed_date_str = parsed_date.isoformat()
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "resposeCode": "01",
                        "responseDescription": "Invalid date format. Use ddmmyyyy.",
                        "data": None
                    }
                )

            # Helper sanitization functions
            def safe_str(v: Optional[str]) -> Optional[str]:
                return v if v and v.strip().lower() not in ("null", "none", "") else None

            def safe_int(v: Optional[str]) -> Optional[int]:
                try:
                    return int(v) if safe_str(v) is not None else None
                except ValueError:
                    return None

            nik = safe_str(nik)
            account_number = safe_str(account_number)
            branch_code = safe_str(branch_code)

            # 
            # query = db.query(ReportMautoCdsbo).filter(
            #     cast(ReportMautoCdsbo.apply_date, Date) == parsed_date
            # )

            # if nik:
            #     query = query.filter(ReportMautoCdsbo.nik == nik)
            # if branch_code is not None:
            #     query = query.filter(ReportMautoCdsbo.branch_code == branch_code)
            # if account_number:
            #     query = query.filter(ReportMautoCdsbo.account_number == account_number)


            # SQL Query pakai bind parameter
            query = text("""
                SELECT * FROM report_mauto_cdsbo 
                WHERE DATE(apply_date) = :apply_date
                AND (:nik IS NULL OR nik = :nik)
                AND (:branch_code IS NULL OR branch_code = :branch_code)
                AND (:account_number IS NULL OR account_number = :account_number)
            """).bindparams(
                bindparam("apply_date"),
                bindparam("nik"),
                bindparam("branch_code"),
                bindparam("account_number"),
            )

            # Parameter dictionary
            params = {
                "apply_date": parsed_date_str,
                "nik": nik,
                "branch_code": branch_code,
                "account_number": account_number
            }

            # Eksekusi query
      

            results = db.execute(query, params).fetchall()
            # Ubah ke list of dict (jika perlu)
            data = [dict(row._mapping) for row in results]

            return {
                "resposeCode": "00",
                "responseDescription": "Success",
                "data": jsonable_encoder(data)
            }

        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "resposeCode": "99",
                    "responseDescription": f"An error occurred while fetching report mauto data: {str(e)}",
                    "data": None
                }
            )
