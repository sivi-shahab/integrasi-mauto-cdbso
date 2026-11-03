from datetime import datetime
from logging import getLogger
from typing import Optional

from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import Date, bindparam, cast, text
from sqlalchemy.orm import Session

from app.models.report_mauto_model import ReportMautoCdsbo
from app.schemas.report_mauto_schema import (
    ReportMautoCdsboBase,
    ReportMautoCdsboRequest,
    ReportMautoCdsboResponse,
)
from app.schemas.response import (
    ResponseCode,
    StandardResponse,
    error_response,
    success_response,
)

logger = getLogger(__name__)


class ReportMautoService:
    @staticmethod
    def get_report_mauto(
        db: Session, request: ReportMautoCdsboRequest, limit: int = 10, offset: int = 0
    ):
        try:
            # Parse apply_date with expected format
            try:
                parsed_date = datetime.strptime(request.apply_date, "%d%m%Y").date()
                parsed_date_str = parsed_date.isoformat()
            except ValueError:
                logger.error("Invalid date format. Use ddmmyyyy.")
                return error_response(
                    ResponseCode.BAD_REQUEST, "Invalid date format. Use ddmmyyyy."
                )

            # Helper sanitization functions
            def safe_str(v: Optional[str]) -> Optional[str]:
                return v if v and v.strip().lower() not in ("null", "none", "") else None

            def safe_int(v: Optional[str]) -> Optional[int]:
                try:
                    return int(v) if safe_str(v) is not None else None
                except ValueError:
                    return None

            nik = safe_str(request.nik)
            account_number = safe_str(request.account_number)
            branch_code = safe_str(request.branch_code)
            cc_reff = safe_str(request.cc_reff)

            # SQL Query pakai bind parameter
            query = text("""
                SELECT * FROM report_mauto_cdsbo
                WHERE DATE(apply_date) = :apply_date
                AND (:nik IS NULL OR nik = :nik)
                AND (:cc_reff IS NULL OR cc_reff = :cc_reff)
                AND (:branch_code IS NULL OR branch_code = :branch_code)
                AND (:account_number IS NULL OR account_number = :account_number)
                LIMIT :limit OFFSET :offset
            """).bindparams(
                bindparam("apply_date"),
                bindparam("nik"),
                bindparam("cc_reff"),
                bindparam("branch_code"),
                bindparam("account_number"),
                bindparam("limit"),
                bindparam("offset"),
            )

            # Parameter dictionary
            params = {
                "apply_date": parsed_date_str,
                "nik": nik,
                "cc_reff": cc_reff,
                "branch_code": branch_code,
                "account_number": account_number,
                "limit": limit,
                "offset": offset,
            }

            # Eksekusi query

            results = db.execute(query, params).fetchall()
            # Ubah ke list of dict (jika perlu)
            data = [dict(row._mapping) for row in results]

            return success_response(data)

        except Exception as e:
            logger.error(f"Exception: {e}")
            return error_response(ResponseCode.INTERNAL_ERROR, "Internal Server Error")
