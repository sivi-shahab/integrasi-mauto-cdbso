from datetime import datetime
from logging import getLogger
from typing import Optional

from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import Date, bindparam, cast, text
from sqlalchemy.orm import Session

from app.schemas.liveness_schema import LivenessRequest
from app.schemas.response import (
    ResponseCode,
    StandardResponse,
    error_response,
    success_response,
)

logger = getLogger(__name__)

class LivenessService:
    @staticmethod
    def get_liveness_data(
        db: Session, request: LivenessRequest, limit: int = 10, offset: int = 0
    ):
        try:
            # SQL Query pakai bind parameter
            query = text("""
                SELECT video_liveness FROM report_mauto_cdsbo_liveness
                WHERE token = :token
            """).bindparams(
                bindparam("token")
            )

            # Parameter dictionary
            params = {
                "token": LivenessRequest.token,
            }

            # Eksekusi query
            results = db.execute(query, params).fetchone()
            # Ubah ke list of dict (jika perlu)
            result_dict = dict(results) if results else None

            return success_response(result_dict)

        except Exception as e:
            logger.error(f"Exception: {e}")
            return error_response(ResponseCode.INTERNAL_ERROR, "Internal Server Error")
