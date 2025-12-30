from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import QObject, pyqtSignal


logger = logging.getLogger(__name__)


class TranslationManager(QObject):
    """
    Runtime translation manager using simple JSON dictionaries per language.

    Translations are stored as ``<language>.json`` (e.g. ``en.json``,
    ``fa.json``) in the configured directory. Each file contains a flat
    mapping of keys to localized strings.

        {
            "login.button": "Login",
            "sidebar.sales": "Sales"
        }

    Usage in code::

        text = translator["login.button"]
        title = translator.translate("main.window_title")

    The manager emits :attr:`language_changed` whenever the active language is
    switched so that views can update their UI.
    """

    language_changed = pyqtSignal(str)

    def __init__(
        self,
        translations_dir: Path,
        default_language: str = "en",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._translations_dir = translations_dir
        self._translations: Dict[str, Dict[str, str]] = {}
        self._current_language: str = default_language

        self._load_translations()

        if self._current_language not in self._translations:
            # Fallback to English if the requested language is not available.
            self._current_language = "en"

    # --------------------------------------------------------------------- #
    # Loading
    # --------------------------------------------------------------------- #
    def _load_translations(self) -> None:
        """
        Load all ``*.json`` files from the translations directory.
        """
        if not self._translations_dir.exists():
            logger.warning(
                "Translations directory %s does not exist.",
                self._translations_dir,
            )
            return

        for path in self._translations_dir.glob("*.json"):
            language_code = path.stem
            try:
                with path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                logger.exception("Failed to load translations from %s", path)
                continue

            if isinstance(data, dict):
                self._translations[language_code] = {
                    str(k): str(v) for k, v in data.items()
                }
                logger.debug(
                    "Loaded %d translations for language '%s'",
                    len(data),
                    language_code,
                )
            else:
                logger.warning(
                    "Translations file %s did not contain a JSON object.", path
                )

    # --------------------------------------------------------------------- #
    # Properties
    # --------------------------------------------------------------------- #
    @property
    def language(self) -> str:
        """
        Return the active language code (e.g. ``\"en\"`` or ``\"fa\"``).
        """
        return self._current_language

    def available_languages(self) -> Dict[str, Dict[str, str]]:
        """
        Return the in-memory translations mapping.

        Keys are language codes and values are dictionaries of
        ``translation_key -> localized_text``.
        """
        return self._translations

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def set_language(self, language_code: str) -> None:
        """
        Activate the given language if translations are available for it.

        Emits :attr:`language_changed` when the language actually changes.
        """
        if language_code == self._current_language:
            return

        if language_code not in self._translations:
            logger.warning("Requested unsupported language '%s'", language_code)
            return

        self._current_language = language_code
        logger.info("Active UI language changed to '%s'", language_code)
        self.language_changed.emit(self._current_language)

    def translate(self, key: str) -> str:
        """
        Return the localized text for ``key`` in the current language.

        If the key is missing in the active language, English is used as a
        fallback. If the key is still not found, the key itself is returned.
        """
        current_map = self._translations.get(self._current_language, {})
        if key in current_map:
            return current_map[key]

        en_map = self._translations.get("en", {})
        if key in en_map:
            return en_map[key]

        return key

    def __getitem__(self, key: str) -> str:
        """
        Dictionary-style access to translations.

        Example::

            login_label = translator["login.username_label"]
        """
        return self.translate(key)