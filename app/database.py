from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Iterator

import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import CONFIG

logger = logging.getLogger(__name__)

# Singleton engine for the entire application
engine = create_engine(
    CONFIG.database_url,
    echo=False,  # Set to True during debugging if you want SQL logging
    future=True,
)

# Factory for new Session objects.  ``expire_on_commit=False`` prevents ORM
# instances from being invalidated after commit, which avoids common
# DetachedInstanceError issues when model instances are passed to the UI layer.
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    Provide a transactional scope around a series of operations.

    Example
    -------
    >>> from app.database import session_scope
    >>> with session_scope() as session:
    ...     # use session here
    ...     ...

    The session is committed if no exception occurs; otherwise it is rolled
    back. In both cases the session is properly closed.
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Session rolled back due to an exception.")
        raise
    finally:
        session.close()


def get_session() -> Generator[Session, None, None]:
    """
    Backwards-compatible generator-based session helper.

    Prefer :func:`session_scope` in new code. This helper simply yields a
    session and ensures it is closed afterwards.
    """
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()