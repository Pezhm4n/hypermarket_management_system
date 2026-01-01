from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR: Path = Path(__file__).resolve().parent
ROOT_DIR: Path = BASE_DIR.parent

# ---------------------------------------------------------------------------
# Loyalty / customer rewards
# ---------------------------------------------------------------------------

# Every LOYALTY_EARN_THRESHOLD units of net spending earns LOYALTY_EARN_RATE point(s).
LOYALTY_EARN_THRESHOLD: int = 100_000
# Monetary value of a single loyalty point.
LOYALTY_POINT_VALUE: int = 1_000
# Points awarded per threshold of spending.
LOYALTY_EARN_RATE: int = 1

# ---------------------------------------------------------------------------
# Hybrid database strategy
# ---------------------------------------------------------------------------

# Toggle this flag to switch between PostgreSQL (False) and SQLite (True).
# For classroom/demo environments PostgreSQL is recommended; for the final
# packaged .exe release SQLite is typically more convenient.
USE_SQLITE: bool = False

# Centralized SQLite configuration so the path is shared across the app.
SQLITE_DB_FILENAME: str = "hypermarket.db"
SQLITE_DB_PATH: Path = ROOT_DIR / SQLITE_DB_FILENAME

# Default PostgreSQL URL (kept for backward compatibility).
POSTGRES_URL: str = (
    "postgresql+psycopg2://postgres:123456@localhost:5432/hms_db"
)


@dataclass(frozen=True)
class AppConfig:
    """
    Application-wide configuration values for the Hypermarket Management System.
    """

    app_name: str = "Hypermarket Management System"
    version: str = "1.0.0"

    # Internationalization
    default_language: str = "fa"  # Supported: "en" (English), "fa" (Persian)
    translations_directory: Path = BASE_DIR / "i18n"

    # Styling
    styles_path: Path = BASE_DIR / "styles" / "main.qss"

    # Database
    # NOTE: Per requirements, the URL is derived from static configuration and
    # does not respect environment variables.
    use_sqlite: bool = USE_SQLITE
    sqlite_db_path: Path = SQLITE_DB_PATH
    database_url: str = (
        f"sqlite:///{SQLITE_DB_PATH}"
        if USE_SQLITE
        else POSTGRES_URL
    )

    # Logging
    log_directory: Path = ROOT_DIR / "logs"


CONFIG = AppConfig()