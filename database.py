from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Update this URL with your PostgreSQL credentials
# Format: postgresql+psycopg2://user:password@host:port/dbname
DATABASE_URL = os.environ.get("DATABASE_URL") or "postgresql+psycopg2://postgres:zxc011@localhost:5432/university"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
