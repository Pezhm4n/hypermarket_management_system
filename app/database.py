import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# In production, set HMS_DATABASE_URL in your environment, e.g.:
# export HMS_DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/hms_db"
DATABASE_URL = os.getenv(
    "HMS_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/hms_db",
)

# Singleton engine for the entire application
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True during debugging if you want SQL logging
    future=True,
)

# Factory for new Session objects
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_session() -> Generator:
    """
    Yield a SQLAlchemy Session and ensure it is properly closed.

    Usage example:

        from app.database import get_session
        import contextlib

        with contextlib.contextmanager(get_session)() as session:
            # use session inside the context
            ...

    This pattern integrates nicely with frameworks that support
    generator-based dependency injection.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()