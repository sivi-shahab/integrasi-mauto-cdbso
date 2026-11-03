from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
import orjson
from pydantic import BaseModel
from enum import Enum

app = FastAPI()


class ResponseCode(str, Enum):
    SUCCESS = "00"
    BAD_REQUEST = "40"
    UNAUTHORIZED = "41"
    FORBIDDEN = "43"
    NOT_FOUND = "44"
    DUPLICATE_DATA = "50"
    INSUFFICIENT_BALANCE = "51"
    LIMIT_EXCEEDED = "52"
    INVALID_STATUS = "53"
    DATABASE_ERROR = "91"
    TIMEOUT = "92"
    EXTERNAL_SERVICE_ERROR = "93"
    INTERNAL_ERROR = "99"


class StandardResponse(BaseModel):
    responseCode: str
    responseDescription: str
    data: dict | list | None = None


def success_response(data, description: str = "Success"):
    return {
        "responseCode": ResponseCode.SUCCESS,
        "responseDescription": description,
        "data": data
    }

def error_response(code: str, description: str):
    return {
        "responseCode": ResponseCode(code),
        "responseDescription": description,
        "data": None
    }


class FastJSONResponse(JSONResponse):
    """JSONResponse dengan serialisasi orjson.

    Kembalikan instance ini langsung dari endpoint agar FastAPI tidak menjalankan
    jsonable_encoder. Output identik dengan JSONResponse standar (separator
    compact, UTF-8, datetime ISO 8601) tetapi jauh lebih cepat untuk response
    besar seperti kolom gambar base64 (README k6 §9.4).
    """

    def render(self, content) -> bytes:
        # Tipe yang tidak didukung orjson (mis. Decimal) memakai aturan FastAPI.
        return orjson.dumps(content, default=jsonable_encoder)
