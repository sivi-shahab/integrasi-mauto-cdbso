from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.configs import settings
from urllib.parse import quote_plus

encoded_user = quote_plus(settings.POSTGRES_USER)
encoded_password = quote_plus(settings.POSTGRES_PASSWORD)

DATABASE_URL = (
    f"postgresql://{encoded_user}:{encoded_password}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)


# hide_parameters: pesan error SQLAlchemy tidak memuat nilai parameter query
# (mis. NIK) sehingga tidak bocor ke log (README k6 §9.3).
engine = create_engine(DATABASE_URL, hide_parameters=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
