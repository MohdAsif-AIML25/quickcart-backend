from collections.abc import Iterator
from sqlalchemy import create_engine 
from sqlalchemy.orm import Session,sessionmaker 
from app.core.config import get_settings 

engine=create_engine(
    get_settings().database_url,
    pool_pre_ping=True,  # test each pooled connection before use
)

SessionLocal=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)

def get_db()->Iterator[Session]:
    """FastAPI dependency: one database session per request, always closed."""
    db=SessionLocal()
    try:
        yield db 

    finally:
        db.close()