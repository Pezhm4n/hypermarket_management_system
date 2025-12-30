from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR: Path = Path(__file__).resolve().parent
ROOT_DIR: Path = BASE_DIR.parent


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
    # NOTE: Per requirements, this is hard-coded and does not respect env vars.
    database_url: str = "postgresql+psycopg2://postgres:123456@localhost:5432/hms_db"

    # Logging
    log_directory: Path = ROOT_DIR / "logs"


CONFIG = AppConfig()