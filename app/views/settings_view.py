from __future__ import annotations

from typing import Optional

import json
import logging
import re
from pathlib import Path

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from qt_material import apply_stylesheet

from app.config import CONFIG, ROOT_DIR
from app.controllers.auth_controller import AuthController
from app.controllers.user_controller import UserController
from app.core.database_manager import DatabaseManager
from app.core.settings_manager import SettingsManager
from app.core.translation_manager import TranslationManager
from app.models.models import UserAccount

logger = logging.getLogger(__name__)


class SettingsView(QWidget):
    """
    Settings / Profile view for the logged-in user.

    Exposes password change, theme selection and font scaling.
    """

    def __init__(
        self,
        auth_controller: AuthController,
        translation_manager: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._auth_controller = auth_controller
        self._translator = translation_manager
        self._current_user: Optional[UserAccount] = None
        self._user_controller = UserController()
        self._profile_data: Optional[dict] = None
        self._store_config_path: Path = ROOT_DIR / "config.json"
        self._store_config: dict = {}
        self._database_manager = DatabaseManager()
        self._db_path: Path = CONFIG.sqlite_db_path

        # Logical base font size used for scaling options (small/medium/large)
        self._base_font_point_size = 12

        self._build_ui()
        self._connect_signals()

        self._translator.language_changed.connect(self._on_language_changed)
        self._apply_translations()
        self._load_ui_preferences()
        self._load_store_settings()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        root_layout.addWidget(scroll_area)

        container = QWidget(scroll_area)
        scroll_area.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # -----------------------------
        # User Profile card
        # -----------------------------
        self.grpProfile = QGroupBox(container)
        self.grpProfile.setObjectName("settingsProfileGroupBox")
        profile_outer_layout = QVBoxLayout(self.grpProfile)
        profile_outer_layout.setContentsMargins(16, 16, 16, 16)
        profile_outer_layout.setSpacing(12)

        profile_grid = QGridLayout()
        profile_grid.setHorizontalSpacing(16)
        profile_grid.setVerticalSpacing(12)

        self.lblProfileFirstName = QLabel(self.grpProfile)
        self.lblProfileLastName = QLabel(self.grpProfile)
        self.lblProfileNationalID = QLabel(self.grpProfile)
        self.lblProfileUsername = QLabel(self.grpProfile)
        self.lblProfileMobile = QLabel(self.grpProfile)

        self.txtProfileFirstName = QLineEdit(self.grpProfile)
        self.txtProfileLastName = QLineEdit(self.grpProfile)
        self.txtProfileNationalID = QLineEdit(self.grpProfile)
        self.txtProfileUsername = QLineEdit(self.grpProfile)
        self.txtProfileMobile = QLineEdit(self.grpProfile)

        # Read-only profile fields
        self.txtProfileFirstName.setReadOnly(True)
        self.txtProfileLastName.setReadOnly(True)
        self.txtProfileNationalID.setReadOnly(True)
        self.txtProfileUsername.setReadOnly(True)

        # Grid layout: 2-column card style (label + field pairs)
        # Row 0: First / Last name
        profile_grid.addWidget(self.lblProfileFirstName, 0, 0)
        profile_grid.addWidget(self.txtProfileFirstName, 0, 1)
        profile_grid.addWidget(self.lblProfileLastName, 0, 2)
        profile_grid.addWidget(self.txtProfileLastName, 0, 3)

        # Row 1: Mobile / National ID
        profile_grid.addWidget(self.lblProfileMobile, 1, 0)
        profile_grid.addWidget(self.txtProfileMobile, 1, 1)
        profile_grid.addWidget(self.lblProfileNationalID, 1, 2)
        profile_grid.addWidget(self.txtProfileNationalID, 1, 3)

        # Row 2: Username spanning both columns
        profile_grid.addWidget(self.lblProfileUsername, 2, 0)
        profile_grid.addWidget(self.txtProfileUsername, 2, 1, 1, 3)

        profile_grid.setColumnStretch(1, 1)
        profile_grid.setColumnStretch(3, 1)

        profile_outer_layout.addLayout(profile_grid)

        # Profile actions row
        self.btnSaveProfile = QPushButton(self.grpProfile)
        self.btnSaveProfile.setObjectName("btnSaveProfile")
        profile_actions = QHBoxLayout()
        profile_actions.addStretch()
        profile_actions.addWidget(self.btnSaveProfile)
        profile_outer_layout.addLayout(profile_actions)

        layout.addWidget(self.grpProfile)

        # -----------------------------
        # Security / Password card
        # -----------------------------
        self.grpSecurity = QGroupBox(container)
        self.grpSecurity.setObjectName("settingsSecurityGroupBox")
        security_outer_layout = QVBoxLayout(self.grpSecurity)
        security_outer_layout.setContentsMargins(16, 16, 16, 16)
        security_outer_layout.setSpacing(12)

        security_grid = QGridLayout()
        security_grid.setHorizontalSpacing(16)
        security_grid.setVerticalSpacing(12)

        self.lblCurrentPassword = QLabel(self.grpSecurity)
        self.txtCurrentPassword = QLineEdit(self.grpSecurity)
        self.txtCurrentPassword.setEchoMode(QLineEdit.EchoMode.Password)

        self.lblNewPassword = QLabel(self.grpSecurity)
        self.txtNewPassword = QLineEdit(self.grpSecurity)
        self.txtNewPassword.setEchoMode(QLineEdit.EchoMode.Password)

        self.lblConfirmPassword = QLabel(self.grpSecurity)
        self.txtConfirmPassword = QLineEdit(self.grpSecurity)
        self.txtConfirmPassword.setEchoMode(QLineEdit.EchoMode.Password)

        # Grid layout: single column of fields
        security_grid.addWidget(self.lblCurrentPassword, 0, 0)
        security_grid.addWidget(self.txtCurrentPassword, 0, 1)

        security_grid.addWidget(self.lblNewPassword, 1, 0)
        security_grid.addWidget(self.txtNewPassword, 1, 1)

        security_grid.addWidget(self.lblConfirmPassword, 2, 0)
        security_grid.addWidget(self.txtConfirmPassword, 2, 1)

        security_grid.setColumnStretch(1, 1)

        security_outer_layout.addLayout(security_grid)

        # Security actions row
        self.btnSavePassword = QPushButton(self.grpSecurity)
        self.btnSavePassword.setObjectName("btnSavePassword")
        security_actions = QHBoxLayout()
        security_actions.addStretch()
        security_actions.addWidget(self.btnSavePassword)
        security_outer_layout.addLayout(security_actions)

        layout.addWidget(self.grpSecurity)

        # -----------------------------
        # Appearance card
        # -----------------------------
        self.grpAppearance = QGroupBox(container)
        self.grpAppearance.setObjectName("settingsAppearanceGroupBox")
        appearance_outer_layout = QVBoxLayout(self.grpAppearance)
        appearance_outer_layout.setContentsMargins(16, 16, 16, 16)
        appearance_outer_layout.setSpacing(12)

        self.lblThemeLabel = QLabel(self.grpAppearance)
        self.cmbTheme = QComboBox(self.grpAppearance)

        self.lblFontScaleLabel = QLabel(self.grpAppearance)
        self.cmbFontScale = QComboBox(self.grpAppearance)

        # Horizontal layout for theme / font scale controls
        appearance_row_layout = QHBoxLayout()
        appearance_row_layout.setSpacing(24)

        theme_column = QVBoxLayout()
        theme_column.setSpacing(6)
        theme_column.addWidget(self.lblThemeLabel)
        theme_column.addWidget(self.cmbTheme)

        font_column = QVBoxLayout()
        font_column.setSpacing(6)
        font_column.addWidget(self.lblFontScaleLabel)
        font_column.addWidget(self.cmbFontScale)

        appearance_row_layout.addLayout(theme_column)
        appearance_row_layout.addLayout(font_column)
        appearance_row_layout.addStretch()

        appearance_outer_layout.addLayout(appearance_row_layout)

        layout.addWidget(self.grpAppearance)

        # Install wheel filters to avoid accidental changes
        self.cmbTheme.installEventFilter(self)
        self.cmbFontScale.installEventFilter(self)

        # -----------------------------
        # Language card
        # -----------------------------
        self.grpLanguage = QGroupBox(container)
        self.grpLanguage.setObjectName("settingsLanguageGroupBox")
        language_outer_layout = QVBoxLayout(self.grpLanguage)
        language_outer_layout.setContentsMargins(16, 16, 16, 16)
        language_outer_layout.setSpacing(12)

        language_row_layout = QHBoxLayout()
        language_row_layout.setSpacing(24)

        self.lblLanguageLabel = QLabel(self.grpLanguage)
        self.cmbLanguage = QComboBox(self.grpLanguage)

        language_row_layout.addWidget(self.lblLanguageLabel)
        language_row_layout.addWidget(self.cmbLanguage)
        language_row_layout.addStretch()

        language_outer_layout.addLayout(language_row_layout)

        layout.addWidget(self.grpLanguage)

        # Install wheel filter for language selector as well
        self.cmbLanguage.installEventFilter(self)

        # -----------------------------
        # Store information card
        # -----------------------------
        self.grpStore = QGroupBox(container)
        self.grpStore.setObjectName("settingsStoreGroupBox")
        store_outer_layout = QVBoxLayout(self.grpStore)
        store_outer_layout.setContentsMargins(16, 16, 16, 16)
        store_outer_layout.setSpacing(12)

        store_grid = QGridLayout()
        store_grid.setHorizontalSpacing(16)
        store_grid.setVerticalSpacing(12)

        self.lblStoreName = QLabel(self.grpStore)
        self.txtStoreName = QLineEdit(self.grpStore)

        self.lblStoreAddress = QLabel(self.grpStore)
        self.txtStoreAddress = QLineEdit(self.grpStore)

        self.lblStorePhone = QLabel(self.grpStore)
        self.txtStorePhone = QLineEdit(self.grpStore)

        store_grid.addWidget(self.lblStoreName, 0, 0)
        store_grid.addWidget(self.txtStoreName, 0, 1)

        store_grid.addWidget(self.lblStoreAddress, 1, 0)
        store_grid.addWidget(self.txtStoreAddress, 1, 1)

        store_grid.addWidget(self.lblStorePhone, 2, 0)
        store_grid.addWidget(self.txtStorePhone, 2, 1)

        store_grid.setColumnStretch(1, 1)

        store_outer_layout.addLayout(store_grid)

        self.btnSaveStore = QPushButton(self.grpStore)
        store_actions = QHBoxLayout()
        store_actions.addStretch()
        store_actions.addWidget(self.btnSaveStore)
        store_outer_layout.addLayout(store_actions)

        layout.addWidget(self.grpStore)

        # -----------------------------
        # Database management card
        # -----------------------------
        self.grpDatabase = QGroupBox(container)
        self.grpDatabase.setObjectName("settingsDatabaseGroupBox")
        db_outer_layout = QVBoxLayout(self.grpDatabase)
        db_outer_layout.setContentsMargins(16, 16, 16, 16)
        db_outer_layout.setSpacing(12)

        db_buttons_layout = QHBoxLayout()
        db_buttons_layout.setSpacing(12)

        self.btnBackupDatabase = QPushButton(self.grpDatabase)
        self.btnRestoreDatabase = QPushButton(self.grpDatabase)

        db_buttons_layout.addWidget(self.btnBackupDatabase)
        db_buttons_layout.addWidget(self.btnRestoreDatabase)
        db_buttons_layout.addStretch()

        db_outer_layout.addLayout(db_buttons_layout)

        layout.addWidget(self.grpDatabase)

        layout.addStretch()

        # Initial options (texts will be overridden by translations)
        self.cmbTheme.addItems(
            [
                "Default (Dark)",
                "Light Mode",
            ]
        )
        self.cmbTheme.setCurrentIndex(0)

        self.cmbFontScale.addItems(
            [
                "Small",
                "Medium",
                "Large",
            ]
        )
        self.cmbFontScale.setCurrentIndex(1)

    def _connect_signals(self) -> None:
        self.btnSaveProfile.clicked.connect(self._on_save_profile_clicked)
        self.btnSavePassword.clicked.connect(self._on_save_password_clicked)
        self.btnSaveStore.clicked.connect(self._on_save_store_clicked)
        self.btnBackupDatabase.clicked.connect(self._on_backup_database_clicked)
        self.btnRestoreDatabase.clicked.connect(self._on_restore_database_clicked)
        self.cmbTheme.currentIndexChanged.connect(self._on_theme_changed)
        self.cmbFontScale.currentIndexChanged.connect(self._on_font_scale_changed)
        if hasattr(self, "cmbLanguage"):
            self.cmbLanguage.currentIndexChanged.connect(
                self._on_language_selection_changed
            )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def set_current_user(self, user: UserAccount) -> None:
        """
        Attach the currently logged-in user to this view.

        The user is required for change-password operations and also
        controls permissions for store/database settings (admin-only).
        """
        try:
            self._current_user = user
            logger.info(
                "SettingsView current user set: UserID=%s, Username=%s",
                getattr(user, "UserID", None),
                getattr(user, "Username", None),
            )
            self._load_profile()
            self._apply_permissions()
        except Exception as e:
            logger.error("Error in set_current_user: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    # ------------------------------------------------------------------ #
    # Translation helpers
    # ------------------------------------------------------------------ #
    def _on_language_changed(self, language: str) -> None:
        try:
            logger.info("SettingsView language changed to: %s", language)
            _ = language  # unused; required by signal signature
            self._apply_translations()
        except Exception as e:
            logger.error("Error in _on_language_changed: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _apply_translations(self) -> None:
        """
        Apply localized texts to labels and buttons.
        """
        try:
            # Window title
            self.setWindowTitle(self._translator["settings.page_title"])

            # Profile section
            if hasattr(self, "grpProfile"):
                self.grpProfile.setTitle(self._translator["settings.profile.title"])
            self.lblProfileFirstName.setText(
                self._translator["users.dialog.field.first_name"]
            )
            self.lblProfileLastName.setText(
                self._translator["users.dialog.field.last_name"]
            )
            self.lblProfileNationalID.setText(
                self._translator["settings.profile.field.national_id"]
            )
            self.lblProfileUsername.setText(
                self._translator["users.dialog.field.username"]
            )
            self.lblProfileMobile.setText(
                self._translator["users.dialog.field.mobile"]
            )
            self.btnSaveProfile.setText(
                self._translator["settings.profile.button.save"]
            )

            # Password section
            if hasattr(self, "grpSecurity"):
                self.grpSecurity.setTitle(
                    self._translator["settings.change_password.title"]
                )
            self.lblCurrentPassword.setText(
                self._translator["settings.change_password.current"]
            )
            self.lblNewPassword.setText(
                self._translator["settings.change_password.new"]
            )
            self.lblConfirmPassword.setText(
                self._translator["settings.change_password.confirm"]
            )
            self.btnSavePassword.setText(
                self._translator["settings.change_password.button"]
            )

            # Appearance section
            if hasattr(self, "grpAppearance"):
                self.grpAppearance.setTitle(
                    self._translator["settings.appearance.title"]
                )
            self.lblThemeLabel.setText(self._translator["settings.theme.label"])
            self.lblFontScaleLabel.setText(
                self._translator["settings.font_scale.label"]
            )

            # Language section
            if hasattr(self, "grpLanguage"):
                self.grpLanguage.setTitle(
                    self._translator.get("settings.language.title", "Language")
                )
            if hasattr(self, "lblLanguageLabel"):
                self.lblLanguageLabel.setText(
                    self._translator.get("settings.language.label", "Application language")
                )

            # Language options
            if hasattr(self, "cmbLanguage"):
                current_lang = getattr(self._translator, "language", "fa")
                self.cmbLanguage.blockSignals(True)
                self.cmbLanguage.clear()
                # Display order: Persian, English
                self.cmbLanguage.addItem(
                    self._translator.get(
                        "settings.language.option.fa",
                        "Persian",
                    ),
                    "fa",
                )
                self.cmbLanguage.addItem(
                    self._translator.get(
                        "settings.language.option.en",
                        "English",
                    ),
                    "en",
                )
                # Select current language
                index = self.cmbLanguage.findData(current_lang)
                if index != -1:
                    self.cmbLanguage.setCurrentIndex(index)
                self.cmbLanguage.blockSignals(False)

            # Theme options
            current_theme = self.cmbTheme.currentIndex()
            self.cmbTheme.blockSignals(True)
            self.cmbTheme.clear()
            # Store the underlying Qt Material theme names as item data so that
            # they can be persisted in SettingsManager.
            self.cmbTheme.addItem(
                self._translator["settings.theme.option.dark_teal"],
                "dark_teal.xml",
            )
            self.cmbTheme.addItem(
                self._translator["settings.theme.option.light"],
                "light_blue.xml",
            )
            if 0 <= current_theme < self.cmbTheme.count():
                self.cmbTheme.setCurrentIndex(current_theme)
            self.cmbTheme.blockSignals(False)

            # Font scale options
            current_scale = self.cmbFontScale.currentIndex()
            self.cmbFontScale.blockSignals(True)
            self.cmbFontScale.clear()
            # Item data holds symbolic keys; actual numeric scale is persisted
            # via SettingsManager.
            self.cmbFontScale.addItem(
                self._translator["settings.font_scale.option.small"], "small"
            )
            self.cmbFontScale.addItem(
                self._translator["settings.font_scale.option.medium"], "medium"
            )
            self.cmbFontScale.addItem(
                self._translator["settings.font_scale.option.large"], "large"
            )
            if 0 <= current_scale < self.cmbFontScale.count():
                self.cmbFontScale.setCurrentIndex(current_scale)
            self.cmbFontScale.blockSignals(False)

            # Store information section
            if hasattr(self, "grpStore"):
                self.grpStore.setTitle(
                    self._translator.get(
                        "settings.store.title",
                        "Store information",
                    )
                )
            if hasattr(self, "lblStoreName"):
                self.lblStoreName.setText(
                    self._translator.get(
                        "settings.store.field.name",
                        "Store name",
                    )
                )
            if hasattr(self, "lblStoreAddress"):
                self.lblStoreAddress.setText(
                    self._translator.get(
                        "settings.store.field.address",
                        "Address",
                    )
                )
            if hasattr(self, "lblStorePhone"):
                self.lblStorePhone.setText(
                    self._translator.get(
                        "settings.store.field.phone",
                        "Phone",
                    )
                )
            if hasattr(self, "btnSaveStore"):
                self.btnSaveStore.setText(
                    self._translator.get(
                        "settings.store.button.save",
                        "Save",
                    )
                )

            # Database section
            if hasattr(self, "grpDatabase"):
                self.grpDatabase.setTitle(
                    self._translator.get(
                        "settings.database.title",
                        "Database",
                    )
                )
            if hasattr(self, "btnBackupDatabase"):
                self.btnBackupDatabase.setText(
                    self._translator.get(
                        "settings.database.button.backup",
                        "Backup",
                    )
                )
            if hasattr(self, "btnRestoreDatabase"):
                self.btnRestoreDatabase.setText(
                    self._translator.get(
                        "settings.database.button.restore",
                        "Restore",
                    )
                )
        except Exception as e:
            logger.error("Error in _apply_translations: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _apply_permissions(self) -> None:
        try:
            is_admin = False
            if self._current_user is not None:
                # Prefer the transient Role attribute attached at login time
                role_title = getattr(self._current_user, "Role", None)
                if not role_title and getattr(self._current_user, "Username", "").lower() == "admin":
                    # Fallback for legacy/default admin without explicit role row
                    role_title = "Admin"
                normalized = (role_title or "").strip().lower()
                is_admin = normalized == "admin"

            # Only admin can manage store info and database
            for widget in (
                getattr(self, "grpStore", None),
                getattr(self, "btnSaveStore", None),
                getattr(self, "grpDatabase", None),
                getattr(self, "btnBackupDatabase", None),
                getattr(self, "btnRestoreDatabase", None),
            ):
                if widget is not None:
                    widget.setEnabled(is_admin)
        except Exception as e:
            logger.error("Error in _apply_permissions: %s", e, exc_info=True)

    # ------------------------------------------------------------------ #
    # Load persisted visual preferences
    # ------------------------------------------------------------------ #
    def _load_ui_preferences(self) -> None:
        """
        Initialise theme, language and font scale selectors from persisted settings.
        """
        try:
            settings = SettingsManager.load_settings()

            # Theme combo
            theme_value = settings.get("theme", "dark_teal.xml")
            if isinstance(theme_value, str):
                index = -1
                for i in range(self.cmbTheme.count()):
                    if self.cmbTheme.itemData(i) == theme_value:
                        index = i
                        break
                if index >= 0:
                    self.cmbTheme.blockSignals(True)
                    self.cmbTheme.setCurrentIndex(index)
                    self.cmbTheme.blockSignals(False)

            # Font scale combo
            raw_scale = settings.get("font_scale", 1.0)
            try:
                scale_value = float(raw_scale)
            except (TypeError, ValueError):
                scale_value = 1.0

            scale_map = {"small": 0.9, "medium": 1.0, "large": 1.1}
            # Find the nearest symbolic scale key
            selected_key = "medium"
            min_diff = float("inf")
            for key, numeric in scale_map.items():
                diff = abs(numeric - scale_value)
                if diff < min_diff:
                    selected_key = key
                    min_diff = diff

            self.cmbFontScale.blockSignals(True)
            font_index = self.cmbFontScale.findData(selected_key)
            if font_index == -1:
                font_index = 1  # medium
            self.cmbFontScale.setCurrentIndex(font_index)
            self.cmbFontScale.blockSignals(False)
            # Apply the font scale to the QApplication
            self._on_font_scale_changed(font_index)

            # Language combo (if present)
            if hasattr(self, "cmbLanguage"):
                current_lang = str(
                    settings.get(
                        "language",
                        getattr(self._translator, "language", "fa"),
                    )
                )
                idx = self.cmbLanguage.findData(current_lang)
                if idx >= 0:
                    self.cmbLanguage.blockSignals(True)
                    self.cmbLanguage.setCurrentIndex(idx)
                    self.cmbLanguage.blockSignals(False)
        except Exception as e:
            logger.error("Error in _load_ui_preferences: %s", e, exc_info=True)

    # ------------------------------------------------------------------ #
    # Theme / font handling
    # ------------------------------------------------------------------ #
    def _on_theme_changed(self, index: int) -> None:
        try:
            logger.info("Theme selection changed to index %s.", index)
            app = QApplication.instance()
            if app is None:
                logger.warning(
                    "QApplication instance is None in _on_theme_changed; aborting."
                )
                return

            # Reset font back to base size before applying a new theme so
            # scaling does not compound across theme switches.
            base_size = getattr(self, "_base_font_point_size", 12)
            base_font = app.font() if app.font() is not None else QFont()
            base_font.setPointSize(base_size)
            app.setFont(base_font)

            theme_data = self.cmbTheme.itemData(index)
            logger.info("Theme data for index %s: %s", index, theme_data)

            theme_name = None
            if isinstance(theme_data, str) and theme_data:
                theme_name = theme_data

            if theme_name and theme_name.endswith(".xml"):
                apply_stylesheet(app, theme=theme_name)
            else:
                # Fallback: restore stylesheet from main.qss
                qss_text = ""
                try:
                    qss_path = CONFIG.styles_path
                    if qss_path.is_file():
                        with qss_path.open(encoding="utf-8") as fh:
                            qss_text = fh.read()
                except Exception as inner_exc:
                    logger.error(
                        "Failed to read stylesheet from disk: %s",
                        inner_exc,
                        exc_info=True,
                    )
                    qss_text = ""
                app.setStyleSheet(qss_text)

            if theme_name:
                SettingsManager.save_setting("theme", theme_name)

            # Re-apply font scaling on top of the theme
            self._on_font_scale_changed(self.cmbFontScale.currentIndex())
        except Exception as e:
            logger.error("Error in _on_theme_changed: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _on_font_scale_changed(self, index: int) -> None:
        try:
            logger.info("Font scale selection changed to index %s.", index)
            app = QApplication.instance()
            if app is None:
                logger.warning(
                    "QApplication instance is None in _on_font_scale_changed; aborting."
                )
                return

            scale_key = self.cmbFontScale.itemData(index)
            if scale_key == "small":
                point_size = 10
                numeric_scale = 0.9
            elif scale_key == "large":
                point_size = 14
                numeric_scale = 1.1
            else:
                point_size = 12
                numeric_scale = 1.0

            logger.info("Applying font point size: %s (scale=%s)", point_size, numeric_scale)

            font = app.font() if app.font() is not None else QFont()
            font.setPointSize(point_size)
            app.setFont(font)

            SettingsManager.save_setting("font_scale", numeric_scale)
        except Exception as e:
            logger.error("Error in _on_font_scale_changed: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def eventFilter(self, obj, event):  # type: ignore[override]
        try:
            if (
                event.type() == QEvent.Type.Wheel
                and isinstance(obj, QComboBox)
                and obj not in (None,)
            ):
                # Allow wheel changes only when the combo has focus or its popup is open.
                view_visible = False
                try:
                    view = obj.view()
                    view_visible = bool(view and view.isVisible())
                except Exception:
                    view_visible = False

                if not obj.hasFocus() and not view_visible:
                    return True
        except Exception as e:
            logger.error("Error in SettingsView.eventFilter: %s", e, exc_info=True)
        return super().eventFilter(obj, event)

    def _on_language_selection_changed(self, index: int) -> None:
        try:
            if not hasattr(self, "cmbLanguage"):
                return
            lang_code = self.cmbLanguage.itemData(index)
            if not lang_code:
                return
            if lang_code == getattr(self._translator, "language", None):
                return
            self._translator.set_language(str(lang_code))
            SettingsManager.save_setting("language", str(lang_code))
        except Exception as e:
            logger.error("Error in _on_language_selection_changed: %s", e, exc_info=True)

    # ------------------------------------------------------------------ #
    # Store settings
    # ------------------------------------------------------------------ #
    def _load_store_settings(self) -> None:
        try:
            if not self._store_config_path:
                return

            if self._store_config_path.is_file():
                with self._store_config_path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    self._store_config = data
                else:
                    self._store_config = {}
            else:
                self._store_config = {}

            store_data = self._store_config.get("store", {})
            if not isinstance(store_data, dict):
                store_data = {}

            self.txtStoreName.setText(str(store_data.get("name", "")))
            self.txtStoreAddress.setText(str(store_data.get("address", "")))
            self.txtStorePhone.setText(str(store_data.get("phone", "")))
        except Exception as e:
            logger.error("Error in _load_store_settings: %s", e, exc_info=True)
            QMessageBox.critical(self, self._translator["dialog.error_title"], str(e))

    def _on_save_store_clicked(self) -> None:
        try:
            if not isinstance(self._store_config, dict):
                self._store_config = {}

            store_data = self._store_config.get("store")
            if not isinstance(store_data, dict):
                store_data = {}
                self._store_config["store"] = store_data

            store_data["name"] = self.txtStoreName.text().strip()
            store_data["address"] = self.txtStoreAddress.text().strip()
            store_data["phone"] = self.txtStorePhone.text().strip()

            tmp_path = self._store_config_path.with_suffix(".tmp")
            self._store_config_path.parent.mkdir(parents=True, exist_ok=True)
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(self._store_config, fh, ensure_ascii=False, indent=2)
            tmp_path.replace(self._store_config_path)

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator.get(
                    "settings.store.info.saved",
                    "Store information saved successfully.",
                ),
            )
        except Exception as e:
            logger.error("Error in _on_save_store_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, self._translator["dialog.error_title"], str(e))

    # ------------------------------------------------------------------ #
    # Profile update
    # ------------------------------------------------------------------ #
    def _load_profile(self) -> None:
        try:
            if self._current_user is None:
                logger.warning(
                    "_load_profile called with no current user; clearing fields."
                )
                self._profile_data = None
                self.txtProfileFirstName.clear()
                self.txtProfileLastName.clear()
                self.txtProfileNationalID.clear()
                self.txtProfileUsername.clear()
                self.txtProfileMobile.clear()
                return

            logger.info(
                "Loading profile for current user: UserID=%s",
                self._current_user.UserID,
            )
            profile = self._user_controller.get_user(self._current_user.UserID)
            self._profile_data = profile

            if not profile:
                logger.warning(
                    "No profile data returned for user_id=%s; clearing fields.",
                    self._current_user.UserID,
                )
                self.txtProfileFirstName.clear()
                self.txtProfileLastName.clear()
                self.txtProfileNationalID.clear()
                self.txtProfileUsername.clear()
                self.txtProfileMobile.clear()
                return

            self.txtProfileFirstName.setText(profile.get("first_name", ""))
            self.txtProfileLastName.setText(profile.get("last_name", ""))
            self.txtProfileNationalID.setText(profile.get("national_id", ""))
            self.txtProfileUsername.setText(profile.get("username", ""))
            self.txtProfileMobile.setText(profile.get("mobile", ""))
        except Exception as e:
            logger.error("Error in _load_profile: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _on_save_profile_clicked(self) -> None:
        try:
            logger.info("Save profile button clicked.")

            if self._current_user is None:
                QMessageBox.critical(
                    self,
                    self._translator["dialog.error_title"],
                    self._translator["settings.change_password.error.no_user"],
                )
                return

            mobile = self.txtProfileMobile.text().strip()
            if not mobile:
                logger.warning("Profile update failed: mobile number is empty.")
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator["settings.profile.error.mobile_required"],
                )
                return

            if not re.fullmatch(r"09\d{9}", mobile):
                logger.warning(
                    "Profile update failed: mobile number invalid value '%s'.",
                    mobile,
                )
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator["settings.profile.error.mobile_invalid"],
                )
                return

            try:
                self._user_controller.update_mobile(
                    user_id=self._current_user.UserID,
                    mobile=mobile,
                )
            except ValueError as exc:
                logger.warning(
                    "Validation error while updating mobile for user_id=%s: %s",
                    self._current_user.UserID,
                    exc,
                )
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    str(exc),
                )
                return

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator["settings.profile.info.updated"],
            )
            logger.info(
                "Profile mobile updated successfully for user_id=%s.",
                self._current_user.UserID,
            )
            self._load_profile()
        except Exception as e:
            logger.error("Error in _on_save_profile_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    # ------------------------------------------------------------------ #
    # Database backup / restore
    # ------------------------------------------------------------------ #
    def _on_backup_database_clicked(self) -> None:
        try:
            db_type = self._database_manager.get_db_type()

            if db_type == "sqlite":
                default_name = "hypermarket_backup.db"
                file_filter = "Database Files (*.db);;All Files (*.*)"
            else:
                default_name = "hms_db_backup.backup"
                file_filter = (
                    "PostgreSQL Backup Files (*.backup *.dump);;All Files (*.*)"
                )

            filename, _ = QFileDialog.getSaveFileName(
                self,
                self._translator.get(
                    "settings.database.backup.dialog_title",
                    "Backup database",
                ),
                default_name,
                file_filter,
            )
            if not filename:
                return

            try:
                self._database_manager.backup_database(filename)
            except FileNotFoundError as exc:
                logger.error(
                    "File not found during database backup: %s",
                    exc,
                    exc_info=True,
                )
                if db_type == "sqlite":
                    message = self._translator.get(
                        "settings.database.error.db_missing",
                        "Database file could not be found.",
                    )
                else:
                    message = str(exc)
                QMessageBox.critical(
                    self,
                    self._translator["dialog.error_title"],
                    message,
                )
                return
            except PermissionError as exc:
                logger.error(
                    "Permission error while creating database backup: %s",
                    exc,
                    exc_info=True,
                )
                QMessageBox.critical(
                    self,
                    self._translator["dialog.error_title"],
                    self._translator.get(
                        "settings.database.error.permission_backup",
                        "Permission denied while creating the backup. Please choose another location or run the application with sufficient permissions.",
                    ),
                )
                return
            except Exception as exc:
                logger.error(
                    "Unexpected error while creating database backup: %s",
                    exc,
                    exc_info=True,
                )
                QMessageBox.critical(
                    self,
                    self._translator["dialog.error_title"],
                    str(exc),
                )
                return

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator.get(
                    "settings.database.backup.success",
                    "Database backup created successfully.",
                ),
            )
        except Exception as e:
            logger.error("Error in _on_backup_database_clicked: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(e),
            )

    def _on_restore_database_clicked(self) -> None:
        try:
            db_type = self._database_manager.get_db_type()

            if db_type == "sqlite":
                file_filter = "Database Files (*.db);;All Files (*.*)"
            else:
                file_filter = (
                    "PostgreSQL Backup Files (*.backup *.dump);;All Files (*.*)"
                )

            filename, _ = QFileDialog.getOpenFileName(
                self,
                self._translator.get(
                    "settings.database.restore.dialog_title",
                    "Restore database",
                ),
                "",
                file_filter,
            )
            if not filename:
                return

            warning_text = self._translator.get(
                "settings.database.restore.warning",
                "This will overwrite current data and restart the app.",
            )
            confirm = QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                warning_text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

            source_path = Path(filename)
            if not source_path.is_file():
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator.get(
                        "settings.database.error.restore_missing",
                        "Selected backup file does not exist.",
                    ),
                )
                return

            try:
                self._database_manager.restore_database(source_path)
            except FileNotFoundError as exc:
                logger.error(
                    "File not found during database restore: %s",
                    exc,
                    exc_info=True,
                )
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator.get(
                        "settings.database.error.restore_missing",
                        str(exc),
                    ),
                )
                return
            except PermissionError as exc:
                logger.error(
                    "Permission error while restoring database: %s",
                    exc,
                    exc_info=True,
                )
                QMessageBox.critical(
                    self,
                    self._translator["dialog.error_title"],
                    self._translator.get(
                        "settings.database.error.permission_restore",
                        "Permission denied while restoring the database. Please close any applications using the file and try again.",
                    ),
                )
                return
            except NotImplementedError as exc:
                logger.warning(
                    "Database restore is not implemented for current backend: %s",
                    exc,
                )
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator.get(
                        "settings.database.restore.not_implemented",
                        str(exc),
                    ),
                )
                return
            except Exception as exc:
                logger.error(
                    "Unexpected error while restoring database: %s",
                    exc,
                    exc_info=True,
                )
                QMessageBox.critical(
                    self,
                    self._translator["dialog.error_title"],
                    str(exc),
                )
                return

            if db_type == "sqlite":
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator.get(
                        "settings.database.restore.success",
                        "Restore successful. The application will now close to apply changes.",
                    ),
                )

                app = QApplication.instance()
                if app is not None:
                    app.quit()
        except Exception as e:
            logger.error(
                "Error in _on_restore_database_clicked: %s",
                e,
                exc_info=True,
            )
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(e),
            )

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_save_password_clicked(self) -> None:
        try:
            logger.info("Save password button clicked.")

            if self._current_user is None:
                QMessageBox.critical(
                    self,
                    self._translator["dialog.error_title"],
                    self._translator["settings.change_password.error.no_user"],
                )
                return

            current = self.txtCurrentPassword.text()
            new = self.txtNewPassword.text()
            confirm = self.txtConfirmPassword.text()

            if not current or not new or not confirm:
                logger.warning(
                    "Password change validation failed: missing current/new/confirm."
                )
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator["settings.change_password.error.required"],
                )
                return

            if new != confirm:
                logger.warning("Password change validation failed: mismatch.")
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator["settings.change_password.error.mismatch"],
                )
                return

            success = self._auth_controller.change_password(
                user_id=self._current_user.UserID,
                current_password=current,
                new_password=new,
            )

            if not success:
                logger.warning(
                    "Password change failed in controller for user_id=%s.",
                    self._current_user.UserID,
                )
                QMessageBox.critical(
                    self,
                    self._translator["dialog.error_title"],
                    self._translator["settings.change_password.error.incorrect"],
                )
                return

            # On success, clear fields and show a confirmation.
            self.txtCurrentPassword.clear()
            self.txtNewPassword.clear()
            self.txtConfirmPassword.clear()

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator["settings.change_password.info.success"],
            )
            logger.info(
                "Password changed successfully for user_id=%s.",
                self._current_user.UserID,
            )
        except Exception as e:
            logger.error("Error in _on_save_password_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))