from collections.abc import Iterator
from venv import create 
from sqlalchemy import create_engine 
from sqlalchemy.orm import Session,sessionmaker 
from app.core.config import get_settings 

engine=create_engine(
    get_settings().database_url,
    poor_pre_ping=True,

)

SessionLocal=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)

def get_db()->Iterator[Session]:
    """FastAPI dependency: one database session per request, always closed."""
    db=SessionLocal()
    try:
        yield db 

    finally:
        db.close()