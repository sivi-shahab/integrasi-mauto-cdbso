from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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