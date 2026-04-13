from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

def get_database_url() -> str:
    """Получить DATABASE_URL и привести к формату SQLAlchemy"""
    url = os.environ.get("DATABASE_URL")

    if not url:
        # Railway может использовать отдельные переменные
        user = os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD", "")
        host = os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("PGPORT") or os.environ.get("POSTGRES_PORT", "5432")
        dbname = os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB", "university")

        if password:
            url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
        else:
            url = f"postgresql+psycopg2://{user}@{host}:{port}/{dbname}"

        print(f"⚠️  DATABASE_URL not set, using fallback: {url.split('@')[-1]}")

    # Railway использует postgresql:// — заменяем на psycopg2
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return url

DATABASE_URL = get_database_url()
print(f"🔗 Connecting to database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'UNKNOWN'}")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
