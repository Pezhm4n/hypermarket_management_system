from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from app.config import ROOT_DIR


logger = logging.getLogger(__name__)


class SettingsManager:
    """
    Lightweight JSON-backed settings helper for user preferences.

    The settings file is stored next to the application root as
    ``user_settings.json`` and currently tracks:

        {
            "theme": "default_dark",
            "language": "fa"
        }

    All methods are classmethods so the manager can be used without
    instantiation.
    """

    _settings_path: Path = ROOT_DIR / "user_settings.json"
    _defaults: Dict[str, Any] = {
        "theme": "default_dark",
        "language": "fa",
    }
    _cache: Dict[str, Any] | None = None

    @classmethod
    def load_settings(cls) -> Dict[str, Any]:
        """
        Load settings from disk, returning a dictionary.

        If the file does not exist, is invalid JSON or does not contain
        a JSON object, the default settings are returned instead.

        A shallow in-memory cache is kept for the lifetime of the process,
        but each call returns a copy so callers cannot accidentally mutate
        the shared state.
        """
        if cls._cache is not None:
            return dict(cls._cache)

        data: Dict[str, Any] = {}
        try:
            if cls._settings_path.is_file():
                with cls._settings_path.open(encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    data = dict(loaded)
                else:
                    logger.warning(
                        "Settings file %s did not contain a JSON object; "
                        "falling back to defaults.",
                        cls._settings_path,
                    )
        except json.JSONDecodeError:
            logger.warning(
                "Settings file %s contained invalid JSON; "
                "falling back to defaults.",
                cls._settings_path,
                exc_info=True,
            )
            data = {}
        except Exception:
            logger.exception(
                "Unexpected error while reading settings from %s; "
                "falling back to defaults.",
                cls._settings_path,
            )
            data = {}

        merged: Dict[str, Any] = dict(cls._defaults)
        merged.update(data)
        cls._cache = merged
        return dict(merged)

    @classmethod
    def save_setting(cls, key: str, value: Any) -> None:
        """
        Persist a single setting key to disk immediately.

        The new value is merged into the current settings, written to a
        temporary file and atomically moved into place to reduce the risk
        of corruption.
        """
        try:
            settings = cls.load_settings()
            settings[key] = value
            cls._cache = dict(settings)

            cls._settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cls._settings_path.with_suffix(".tmp")

            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(settings, fh, ensure_ascii=False, indent=2)

            tmp_path.replace(cls._settings_path)
            logger.info("Persisted setting '%s' to %s", key, cls._settings_path)
        except Exception:
            logger.exception("Failed to persist setting '%s'", key)

    @classmethod
    def get_setting(cls, key: str, default: Any = None) -> Any:
        """
        Retrieve a single setting value with a fallback.

        This is a thin wrapper around :meth:`load_settings`.
        """
        settings = cls.load_settings()
        return settings.get(key, default)