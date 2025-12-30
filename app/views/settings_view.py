from __future__ import annotations

from typing import Optional

import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from qt_material import apply_stylesheet

from app.config import CONFIG
from app.controllers.auth_controller import AuthController
from app.controllers.user_controller import UserController
from app.core.translation_manager import TranslationManager
from app.models.models import UserAccount


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

        self._build_ui()
        self._connect_signals()

        self._translator.language_changed.connect(self._on_language_changed)
        self._apply_translations()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Profile section
        self.lblProfileTitle = QLabel(self)
        self.lblProfileTitle.setObjectName("settingsProfileTitleLabel")

        profile_layout = QFormLayout()
        profile_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        profile_layout.setFormAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        profile_layout.setHorizontalSpacing(12)
        profile_layout.setVerticalSpacing(12)

        self.txtProfileFirstName = QLineEdit(self)
        self.txtProfileLastName = QLineEdit(self)
        self.txtProfileNationalID = QLineEdit(self)
        self.txtProfileUsername = QLineEdit(self)
        self.txtProfileMobile = QLineEdit(self)

        # Read-only fields
        self.txtProfileFirstName.setReadOnly(True)
        self.txtProfileLastName.setReadOnly(True)
        self.txtProfileNationalID.setReadOnly(True)
        self.txtProfileUsername.setReadOnly(True)

        self.lblProfileFirstName = QLabel(self)
        self.lblProfileLastName = QLabel(self)
        self.lblProfileNationalID = QLabel(self)
        self.lblProfileUsername = QLabel(self)
        self.lblProfileMobile = QLabel(self)

        profile_layout.addRow(self.lblProfileFirstName, self.txtProfileFirstName)
        profile_layout.addRow(self.lblProfileLastName, self.txtProfileLastName)
        profile_layout.addRow(self.lblProfileNationalID, self.txtProfileNationalID)
        profile_layout.addRow(self.lblProfileUsername, self.txtProfileUsername)
        profile_layout.addRow(self.lblProfileMobile, self.txtProfileMobile)

        self.btnSaveProfile = QPushButton(self)
        self.btnSaveProfile.setObjectName("btnSaveProfile")

        layout.addWidget(self.lblProfileTitle)
        layout.addLayout(profile_layout)
        layout.addWidget(
            self.btnSaveProfile,
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        # Password section
        self.lblTitle = QLabel(self)
        self.lblTitle.setObjectName("settingsTitleLabel")

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        form_layout.setFormAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(12)

        self.lblCurrentPassword = QLabel(self)
        self.txtCurrentPassword = QLineEdit(self)
        self.txtCurrentPassword.setEchoMode(QLineEdit.EchoMode.Password)

        self.lblNewPassword = QLabel(self)
        self.txtNewPassword = QLineEdit(self)
        self.txtNewPassword.setEchoMode(QLineEdit.EchoMode.Password)

        self.lblConfirmPassword = QLabel(self)
        self.txtConfirmPassword = QLineEdit(self)
        self.txtConfirmPassword.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout.addRow(self.lblCurrentPassword, self.txtCurrentPassword)
        form_layout.addRow(self.lblNewPassword, self.txtNewPassword)
        form_layout.addRow(self.lblConfirmPassword, self.txtConfirmPassword)

        self.btnSavePassword = QPushButton(self)
        self.btnSavePassword.setObjectName("btnSavePassword")

        layout.addWidget(self.lblTitle)
        layout.addLayout(form_layout)
        layout.addWidget(
            self.btnSavePassword,
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        # Appearance section
        self.lblAppearanceTitle = QLabel(self)
        self.lblThemeLabel = QLabel(self)
        self.cmbTheme = QComboBox(self)

        self.lblFontScaleLabel = QLabel(self)
        self.cmbFontScale = QComboBox(self)

        appearance_layout = QFormLayout()
        appearance_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        appearance_layout.setFormAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        appearance_layout.setHorizontalSpacing(12)
        appearance_layout.setVerticalSpacing(8)

        appearance_layout.addRow(self.lblThemeLabel, self.cmbTheme)
        appearance_layout.addRow(self.lblFontScaleLabel, self.cmbFontScale)

        layout.addSpacing(16)
        layout.addWidget(self.lblAppearanceTitle)
        layout.addLayout(appearance_layout)

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
        self.cmbTheme.currentIndexChanged.connect(self._on_theme_changed)
        self.cmbFontScale.currentIndexChanged.connect(self._on_font_scale_changed)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def set_current_user(self, user: UserAccount) -> None:
        """
        Attach the currently logged-in user to this view.

        The user is required for change-password operations.
        """
        self._current_user = user
        self._load_profile()

    # ------------------------------------------------------------------ #
    # Translation helpers
    # ------------------------------------------------------------------ #
    def _on_language_changed(self, language: str) -> None:
        _ = language  # unused; required by signal signature
        self._apply_translations()

    def _apply_translations(self) -> None:
        """
        Apply localized texts to labels and buttons.
        """
        # Window title
        self.setWindowTitle(self._translator["settings.page_title"])

        # Profile section
        self.lblProfileTitle.setText("Profile")
        self.lblProfileFirstName.setText(
            self._translator["users.dialog.field.first_name"]
        )
        self.lblProfileLastName.setText(
            self._translator["users.dialog.field.last_name"]
        )
        self.lblProfileNationalID.setText("National ID")
        self.lblProfileUsername.setText(
            self._translator["users.dialog.field.username"]
        )
        self.lblProfileMobile.setText(self._translator["users.dialog.field.mobile"])
        self.btnSaveProfile.setText("Save profile")

        # Password section
        self.lblTitle.setText(self._translator["settings.change_password.title"])
        self.lblCurrentPassword.setText(
            self._translator["settings.change_password.current"]
        )
        self.lblNewPassword.setText(self._translator["settings.change_password.new"])
        self.lblConfirmPassword.setText(
            self._translator["settings.change_password.confirm"]
        )
        self.btnSavePassword.setText(
            self._translator["settings.change_password.button"]
        )

        # Appearance section
        self.lblAppearanceTitle.setText(
            self._translator["settings.appearance.title"]
        )
        self.lblThemeLabel.setText(self._translator["settings.theme.label"])
        self.lblFontScaleLabel.setText(
            self._translator["settings.font_scale.label"]
        )

        # Theme options
        current_theme = self.cmbTheme.currentIndex()
        self.cmbTheme.blockSignals(True)
        self.cmbTheme.clear()
        self.cmbTheme.addItem(
            self._translator["settings.theme.option.dark_teal"], "default"
        )
        self.cmbTheme.addItem(
            self._translator["settings.theme.option.light"], "light"
        )
        if 0 <= current_theme < self.cmbTheme.count():
            self.cmbTheme.setCurrentIndex(current_theme)
        self.cmbTheme.blockSignals(False)

        # Font scale options
        current_scale = self.cmbFontScale.currentIndex()
        self.cmbFontScale.blockSignals(True)
        self.cmbFontScale.clear()
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

    # ------------------------------------------------------------------ #
    # Theme / font handling
    # ------------------------------------------------------------------ #
    def _on_theme_changed(self, index: int) -> None:
        app = QApplication.instance()
        if app is None:
            return

        theme_data = self.cmbTheme.itemData(index)
        if theme_data == "light":
            apply_stylesheet(app, theme="light_blue.xml")
        else:
            # Default dark: restore base stylesheet from main.qss
            qss_text = ""
            try:
                qss_path = CONFIG.styles_path
                if qss_path.is_file():
                    with qss_path.open(encoding="utf-8") as fh:
                        qss_text = fh.read()
            except Exception:
                qss_text = ""
            app.setStyleSheet(qss_text)

        # Re-apply font scale override on top of the theme
        self._on_font_scale_changed(self.cmbFontScale.currentIndex())

    def _on_font_scale_changed(self, index: int) -> None:
        app = QApplication.instance()
        if app is None:
            return

        scale = self.cmbFontScale.itemData(index)
        if scale == "small":
            point_size = 10
        elif scale == "large":
            point_size = 14
        else:
            point_size = 12

        font = app.font() if app.font() is not None else QFont()
        font.setPointSize(point_size)
        app.setFont(font)

        # Force global font size via stylesheet override
        base_qss = app.styleSheet() or ""
        marker = "/* FONT_SCALE_OVERRIDE */"
        if marker in base_qss:
            base_qss = base_qss.split(marker)[0].rstrip()

        override = f"\n{marker}\n* {{ font-size: {point_size}pt; }}\n"
        app.setStyleSheet(base_qss + override)

    # ------------------------------------------------------------------ #
    # Profile update
    # ------------------------------------------------------------------ #
    def _load_profile(self) -> None:
        if self._current_user is None:
            self._profile_data = None
            self.txtProfileFirstName.clear()
            self.txtProfileLastName.clear()
            self.txtProfileNationalID.clear()
            self.txtProfileUsername.clear()
            self.txtProfileMobile.clear()
            return

        profile = self._user_controller.get_user(self._current_user.UserID)
        self._profile_data = profile

        if not profile:
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

    def _on_save_profile_clicked(self) -> None:
        if self._current_user is None:
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                self._translator["settings.change_password.error.no_user"],
            )
            return

        mobile = self.txtProfileMobile.text().strip()
        if not mobile:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                "Mobile number is required.",
            )
            return

        if not re.fullmatch(r"09\d{9}", mobile):
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                "Mobile number must start with '09' and be 11 digits.",
            )
            return

        try:
            self._user_controller.update_mobile(
                user_id=self._current_user.UserID,
                mobile=mobile,
            )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                str(exc),
            )
            return
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )
            return

        QMessageBox.information(
            self,
            self._translator["dialog.info_title"],
            "Profile updated successfully.",
        )
        self._load_profile()

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_save_password_clicked(self) -> None:
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
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                self._translator["settings.change_password.error.required"],
            )
            return

        if new != confirm:
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