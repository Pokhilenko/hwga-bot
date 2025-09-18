from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dota_analytics.config import settings

engine = create_engine(settings.DOTA_DB_DSN)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
