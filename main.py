from __future__ import annotations

import logging
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from sqlalchemy.exc import SQLAlchemyError

from app.config import CONFIG
from app.controllers.auth_controller import AuthController
from app.core.logging_config import configure_logging
from app.core.translation_manager import TranslationManager
from app.database import engine
from app.models.models import Base  # importing this registers all model classes
from app.views.login_view import LoginView
from app.views.main_view import MainView


logger = logging.getLogger(__name__)


def init_database() -> None:
    """
    Initialize the database schema if it does not already exist.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database connection successful; tables created/verified.")
    except SQLAlchemyError:
        logger.exception("Database initialization failed.")
        # Re-raise so the application can fail fast during startup.
        raise


class Application:
    """
    Top-level Qt application wiring together initialization, views and controllers.
    """

    def __init__(self) -> None:
        # Configure logging before anything else so startup issues are captured.
        configure_logging(CONFIG.log_directory)

        self.qt_app = QApplication(sys.argv)
        self.qt_app.setApplicationName(CONFIG.app_name)
        self.qt_app.setApplicationVersion(CONFIG.version)

        self._load_stylesheet()

        # Internationalization
        self.translation_manager = TranslationManager(
            translations_dir=CONFIG.translations_directory,
            default_language=CONFIG.default_language,
        )
        self._apply_layout_direction()

        # Database and default admin
        init_database()
        self.auth_controller = AuthController()
        self.auth_controller.create_default_admin()

        # Views
        self.main_view = MainView(
            auth_controller=self.auth_controller,
            translation_manager=self.translation_manager,
        )
        self.login_view = LoginView(
            auth_controller=self.auth_controller,
            translation_manager=self.translation_manager,
        )

        self._connect_signals()

    # ------------------------------------------------------------------ #
    # Initialize look & feel
    # ------------------------------------------------------------------ #
    def _load_stylesheet(self) -> None:
        """
        Load the global QSS stylesheet from disk.
        """
        try:
            qss_path = CONFIG.styles_path
            if qss_path.is_file():
                with qss_path.open(encoding="utf-8") as fh:
                    self.qt_app.setStyleSheet(fh.read())
            else:
                logger.warning(
                    "Stylesheet %s not found; running without custom styles.",
                    qss_path,
                )
        except Exception:
            logger.exception("Failed to load application stylesheet.")

    def _apply_layout_direction(self) -> None:
        """
        Apply RTL/LTR layout direction based on the active language.
        """
        if self.translation_manager.language == "fa":
            self.qt_app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.qt_app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    # ------------------------------------------------------------------ #
    # Signal wiring
    # ------------------------------------------------------------------ #
    def _connect_signals(self) -> None:
        # Login flow
        self.login_view.login_success.connect(self._on_login_success)

        # Logout flow
        self.main_view.logout_requested.connect(self._on_logout_requested)

        # React to language changes
        self.translation_manager.language_changed.connect(
            self._on_language_changed
        )

    # ------------------------------------------------------------------ #
    # Slots / event handlers
    # ------------------------------------------------------------------ #
    def _on_login_success(self, user) -> None:
        """
        Handle a successful login emitted from the login view.
        """
        self.main_view.set_logged_in_user(user)
        self.main_view.show()
        self.login_view.close()

    def _on_logout_requested(self) -> None:
        """
        Handle logout from the main view by returning to the login screen.
        """
        self.main_view.hide()
        # Re-create the login view to clear any stale state.
        self.login_view = LoginView(
            auth_controller=self.auth_controller,
            translation_manager=self.translation_manager,
        )
        self.login_view.login_success.connect(self._on_login_success)
        self.login_view.show()

    def _on_language_changed(self, language: str) -> None:
        """
        Keep the Qt layout direction in sync with the active language.
        """
        _ = language
        self._apply_layout_direction()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(self) -> int:
        """
        Show the login view and enter the Qt event loop.
        """
        self.login_view.show()
        return self.qt_app.exec()


def main() -> None:
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()