from __future__ import annotations

import logging
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from qt_material import apply_stylesheet
from sqlalchemy import text, inspect, Integer, Numeric
from sqlalchemy.exc import SQLAlchemyError

from app.config import CONFIG
from app.controllers.auth_controller import AuthController
from app.core.database_manager import DatabaseManager
from app.core.logging_config import configure_logging
from app.core.settings_manager import SettingsManager
from app.core.translation_manager import TranslationManager
from app.database import engine
from app.models.models import Base  # importing this registers all model classes
from app.views.login_view import LoginView
from app.views.main_view import MainView


logger = logging.getLogger(__name__)


def init_database() -> None:
    """
    Initialize the database schema and apply lightweight self-healing migrations.

    This function will:
      * Create tables that do not exist.
      * For PostgreSQL: add missing columns and adjust column types where required
        (e.g., MinStockLevel to NUMERIC).
      * For SQLite: only ensure tables exist (no raw SQL migrations).
    """
    try:
        # Ensure all tables defined in the ORM exist (works for both backends).
        Base.metadata.create_all(bind=engine)

        db_type = DatabaseManager().get_db_type()
        if db_type != "postgres":
            logger.info(
                "Skipping PostgreSQL-specific migrations for backend '%s'.", db_type
            )
            logger.info("Database connection successful; tables created/verified.")
            return

        inspector = inspect(engine)

        with engine.begin() as conn:
            # ------------------------------------------------------------------
            # Shift: ensure CashFloat exists
            # ------------------------------------------------------------------
            try:
                if inspector.has_table("shift"):
                    shift_columns = {
                        col["name"]: col for col in inspector.get_columns("shift")
                    }
                    if "CashFloat" not in shift_columns:
                        conn.execute(
                            text(
                                'ALTER TABLE "shift" '
                                'ADD COLUMN "CashFloat" NUMERIC(15, 2);'
                            )
                        )
                        logger.info("Added missing column shift.CashFloat")
            except Exception:
                logger.exception("Failed to ensure shift.CashFloat column exists")

            # ------------------------------------------------------------------
            # Product: ensure Unit, IsActive, and MinStockLevel type
            # ------------------------------------------------------------------
            try:
                if inspector.has_table("product"):
                    product_columns = {
                        col["name"]: col for col in inspector.get_columns("product")
                    }

                    if "Unit" not in product_columns:
                        conn.execute(
                            text(
                                'ALTER TABLE "product" '
                                "ADD COLUMN \"Unit\" VARCHAR(20) DEFAULT 'Pcs';"
                            )
                        )
                        logger.info("Added missing column product.Unit")

                    if "IsActive" not in product_columns:
                        conn.execute(
                            text(
                                'ALTER TABLE "product" '
                                'ADD COLUMN "IsActive" BOOLEAN DEFAULT TRUE;'
                            )
                        )
                        logger.info("Added missing column product.IsActive")

                    min_stock_col = product_columns.get("MinStockLevel")
                    if min_stock_col is not None:
                        col_type = min_stock_col.get("type")
                        # If existing type is Integer, migrate to NUMERIC(12, 2)
                        if isinstance(col_type, Integer):
                            conn.execute(
                                text(
                                    'ALTER TABLE "product" '
                                    'ALTER COLUMN "MinStockLevel" '
                                    'TYPE NUMERIC(12, 2) '
                                    'USING "MinStockLevel"::numeric;'
                                )
                            )
                            logger.info(
                                "Migrated product.MinStockLevel from INTEGER to NUMERIC(12, 2)"
                            )
            except Exception:
                logger.exception("Failed to apply product column migrations")

            # ------------------------------------------------------------------
            # Invoice: ensure Discount column exists
            # ------------------------------------------------------------------
            try:
                if inspector.has_table("invoice"):
                    invoice_columns = {
                        col["name"]: col for col in inspector.get_columns("invoice")
                    }
                    if "Discount" not in invoice_columns:
                        conn.execute(
                            text(
                                'ALTER TABLE "invoice" '
                                'ADD COLUMN "Discount" NUMERIC(15, 2) DEFAULT 0;'
                            )
                        )
                        logger.info("Added missing column invoice.Discount")
            except Exception:
                logger.exception("Failed to ensure invoice.Discount column exists")

        logger.info("Database connection successful; tables created/verified.")
    except SQLAlchemyError:
        logger.exception("Database initialization failed.")
        # Re-raise so the application can fail fast during startup.
        raise
    except Exception:
        logger.exception("Unexpected error during database initialization.")
        raise


class Application:
    """
    Top-level Qt application wiring together initialization, views and controllers.
    """

    def __init__(self) -> None:
        # Configure logging before anything else so startup issues are captured.
        configure_logging(CONFIG.log_directory)

        # Load persisted UI settings (theme / language / font scale)
        self._settings = SettingsManager.load_settings()

        self.qt_app = QApplication(sys.argv)
        self.qt_app.setApplicationName(CONFIG.app_name)
        self.qt_app.setApplicationVersion(CONFIG.version)

        # Apply theme and font scale based on saved settings
        self._load_stylesheet()

        # Internationalization
        self.translation_manager = TranslationManager(
            translations_dir=CONFIG.translations_directory,
            default_language=self._settings.get("language", CONFIG.default_language),
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
        Apply the saved theme (Qt Material XML or QSS fallback) and font scale.
        """
        try:
            settings = getattr(self, "_settings", {}) or {}
            theme_value = settings.get("theme", "dark_teal.xml")

            if isinstance(theme_value, str) and theme_value.endswith(".xml"):
                apply_stylesheet(self.qt_app, theme=theme_value)
            else:
                self._load_stylesheet_from_qss()

            self._apply_font_scale_from_settings()
        except Exception:
            logger.exception(
                "Failed to apply theme from settings; falling back to QSS + default font."
            )
            try:
                self._load_stylesheet_from_qss()
            except Exception:
                # Fallback already logged
                pass

    def _load_stylesheet_from_qss(self) -> None:
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

    def _apply_font_scale_from_settings(self) -> None:
        """
        Apply a global font size based on the persisted font_scale value.
        """
        try:
            settings = getattr(self, "_settings", {}) or {}
            raw_scale = settings.get("font_scale", 1.0)
            try:
                scale_value = float(raw_scale)
            except (TypeError, ValueError):
                scale_value = 1.0

            # Map the numeric scale to one of the discrete sizes used in SettingsView.
            if scale_value <= 0.95:
                point_size = 10  # small
            elif scale_value >= 1.05:
                point_size = 14  # large
            else:
                point_size = 12  # medium

            font = self.qt_app.font()
            font.setPointSize(point_size)
            self.qt_app.setFont(font)
        except Exception:
            logger.exception("Failed to apply font scale from settings.")

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
        Keep the Qt layout direction in sync with the active language and
        persist the choice so it is restored on next startup.
        """
        self._apply_layout_direction()
        try:
            SettingsManager.save_setting("language", str(language))
        except Exception:
            logger.exception("Failed to persist language change '%s'", language)

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