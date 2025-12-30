from __future__ import annotations

from typing import Optional

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

from app.controllers.auth_controller import AuthController
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

        # Initial options
        self.cmbTheme.addItems(
            [
                "Dark Teal",
                "Light",
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
            self._translator["settings.theme.option.dark_teal"], "dark"
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
            apply_stylesheet(app, theme="dark_teal.xml")

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