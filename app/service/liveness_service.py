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
        db: Session, request: LivenessRequest
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
                "token": request.token,
            }

            # Eksekusi query
            cursor = db.execute(query, params)
            results = cursor.fetchone()


            if results:
                columns = cursor.keys()
                result_dict = dict(zip(columns, results))
            else:
                return error_response(ResponseCode.NOT_FOUND, "Data Not Found")

            return success_response(result_dict)

        except Exception as e:
            logger.error(f"Exception: {e}")
            return error_response(ResponseCode.INTERNAL_ERROR, "Internal Server Error")
