from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.core.configs import settings
from app.schemas.response import ResponseCode

API_KEY_NAME = settings.API_KEY_NAME
VALID_API_KEYS = settings.VALID_API_KEYS
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def validate_api_key(api_key: str = Security(api_key_header)):
    """Validasi API Key dari request header"""
    if not api_key or api_key != VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return api_key