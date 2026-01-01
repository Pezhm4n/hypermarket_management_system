from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.engine.url import make_url

from app.config import CONFIG, SQLITE_DB_PATH, USE_SQLITE

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    High-level helper for backing up and restoring the application database.

    The manager abstracts differences between PostgreSQL and SQLite so that the
    UI can invoke a single API regardless of the configured backend.
    """

    def __init__(self) -> None:
        self._config = CONFIG

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def get_db_type(self) -> str:
        """
        Return the current database backend type: ``\"sqlite\"`` or ``\"postgres\"``.
        """
        if USE_SQLITE:
            return "sqlite"

        url = make_url(self._config.database_url)
        backend = (url.get_backend_name() or "").lower()
        if backend.startswith("sqlite"):
            return "sqlite"
        return "postgres"

    # ------------------------------------------------------------------ #
    # Backup
    # ------------------------------------------------------------------ #
    def backup_database(self, destination_path: str | Path) -> None:
        """
        Create a backup of the active database at ``destination_path``.

        Parameters
        ----------
        destination_path:
            Target file path for the backup.

        Raises
        ------
        FileNotFoundError
            If the SQLite DB file is missing or ``pg_dump`` is not available.
        PermissionError
            If the backup file cannot be written due to file system permissions.
        RuntimeError
            If ``pg_dump`` exits with a non-zero status code.
        """
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        db_type = self.get_db_type()
        logger.info("Starting %s database backup to %s", db_type, dest)

        if db_type == "sqlite":
            self._backup_sqlite(dest)
        else:
            self._backup_postgres(dest)

    def _backup_sqlite(self, destination: Path) -> None:
        source = SQLITE_DB_PATH
        if not source.is_file():
            raise FileNotFoundError(
                f"SQLite database file could not be found at: {source}"
            )

        shutil.copy2(source, destination)

    def _backup_postgres(self, destination: Path) -> None:
        """
        Use ``pg_dump`` to create a PostgreSQL backup.

        The password is provided via the ``PGPASSWORD`` environment variable
        (never embedded in the command line).
        """
        url = make_url(self._config.database_url)

        db_name = url.database or "hms_db"
        user = url.username or "postgres"
        host = url.host or "localhost"
        port = url.port or 5432

        env = os.environ.copy()
        if url.password and "PGPASSWORD" not in env:
            # Do not interpolate the password into the command string.
            env["PGPASSWORD"] = url.password

        cmd = [
            "pg_dump",
            "-h",
            host,
            "-p",
            str(port),
            "-U",
            user,
            "-F",
            "c",
            "-b",
            "-v",
            "-f",
            str(destination),
            db_name,
        ]

        logger.debug("Running pg_dump command: %s", " ".join(cmd))

        try:
            completed = subprocess.run(
                cmd,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            if completed.stderr:
                logger.info("pg_dump stderr: %s", completed.stderr.strip())
        except FileNotFoundError as exc:
            logger.exception("pg_dump command not found.")
            # Propagate a clear error that the UI can show to the user.
            raise FileNotFoundError(
                "pg_dump command not found. Please install PostgreSQL client "
                "tools and ensure 'pg_dump' is available on your PATH."
            ) from exc
        except subprocess.CalledProcessError as exc:
            logger.exception("pg_dump failed with exit code %s", exc.returncode)
            stderr = exc.stderr.strip() if exc.stderr else str(exc)
            raise RuntimeError(f"pg_dump failed: {stderr}") from exc

    # ------------------------------------------------------------------ #
    # Restore
    # ------------------------------------------------------------------ #
    def restore_database(self, source_path: str | Path) -> None:
        """
        Restore the database from ``source_path``.

        For SQLite this overwrites the existing ``.db`` file after disposing
        the SQLAlchemy engine to release file handles. For PostgreSQL this
        method intentionally raises :class:`NotImplementedError` for safety.
        """
        src = Path(source_path)
        if not src.is_file():
            raise FileNotFoundError(f"Backup file does not exist: {src}")

        db_type = self.get_db_type()
        logger.info("Starting %s database restore from %s", db_type, src)

        if db_type == "sqlite":
            self._restore_sqlite(src)
        else:
            raise NotImplementedError(
                "Restore for PostgreSQL must be done via pgAdmin or psql for "
                "safety. The application does not perform automated in-place "
                "PostgreSQL restores."
            )

    def _restore_sqlite(self, source: Path) -> None:
        # Dispose existing engine connections to release file handles.
        from app.database import engine  # Local import to avoid circular import.

        engine.dispose()

        target = SQLITE_DB_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)