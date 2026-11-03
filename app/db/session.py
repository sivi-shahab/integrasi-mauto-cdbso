from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.configs import settings

encoded_user = quote_plus(settings.POSTGRES_USER)
encoded_password = quote_plus(settings.POSTGRES_PASSWORD)

DATABASE_URL = (
    f"postgresql://{encoded_user}:{encoded_password}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)

APPLICATION_NAME = "report-mauto-cdsbo"


def pool_settings() -> dict:
    """Konfigurasi pool per worker dari env (README k6 §9.1/§9.2)."""
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_pre_ping": True,  # deteksi koneksi yang diputus DB/firewall sebelum dipakai
    }


def check_connection_budget(workers: int) -> int:
    """Total koneksi maksimum service = workers x (pool_size + max_overflow).

    Raise ValueError jika melebihi DB_CONNECTION_BUDGET agar service gagal start
    alih-alih menghabiskan max_connections PostgreSQL yang dipakai service lain.
    """
    per_worker = settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW
    total = workers * per_worker
    if total > settings.DB_CONNECTION_BUDGET:
        raise ValueError(
            f"Total koneksi DB {total} (APP_WORKERS={workers} x (DB_POOL_SIZE={settings.DB_POOL_SIZE} + "
            f"DB_MAX_OVERFLOW={settings.DB_MAX_OVERFLOW})) melebihi DB_CONNECTION_BUDGET="
            f"{settings.DB_CONNECTION_BUDGET}"
        )
    return total


# hide_parameters: pesan error SQLAlchemy tidak memuat nilai parameter query
# (mis. NIK) sehingga tidak bocor ke log (README k6 §9.3).
# application_name: memudahkan DBA memantau koneksi service ini di pg_stat_activity.
engine = create_engine(
    DATABASE_URL,
    hide_parameters=True,
    connect_args={"application_name": APPLICATION_NAME},
    **pool_settings(),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
