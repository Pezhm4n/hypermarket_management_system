from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.models.models import Base  # importing this registers all model classes


def init_database() -> None:
    try:
        # Create all tables defined on Base.metadata
        Base.metadata.create_all(bind=engine)
        print("Database Connection Successful & Tables Created")
    except SQLAlchemyError as exc:
        # In Phase 1 we just print; later you may log this properly.
        print("Database initialization failed:", exc)


if __name__ == "__main__":
    init_database()