from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    PROJECT_NAME: str = "Loyalty Program API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/v1"
    POSTGRES_HOST : str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: str
    API_KEY_NAME: str
    VALID_API_KEYS: str

    class Config:
        case_sensitive = True
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
