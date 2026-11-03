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

    # Server (README k6 §9.2): jumlah proses worker uvicorn saat `python main.py`.
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8013
    APP_WORKERS: int = 1

    # Connection pool DB per worker (README k6 §9.1/§9.2).
    DB_POOL_SIZE: int = 5          # koneksi tetap per worker
    DB_MAX_OVERFLOW: int = 5       # koneksi tambahan saat ramai, per worker
    DB_POOL_TIMEOUT: int = 10      # detik menunggu koneksi kosong sebelum error (fail fast)
    DB_POOL_RECYCLE: int = 1800    # detik; koneksi lebih tua dari ini dibuat ulang
    # Batas total koneksi service ke PostgreSQL = APP_WORKERS x (DB_POOL_SIZE + DB_MAX_OVERFLOW).
    # Service menolak start jika melebihi. Sepakati nilainya dengan DBA (sisa max_connections).
    DB_CONNECTION_BUDGET: int = 100

    class Config:
        case_sensitive = True
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
