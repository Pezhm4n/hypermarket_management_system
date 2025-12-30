from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.controllers.auth_controller import AuthController
from app.core.translation_manager import TranslationManager
from app.models.models import UserAccount


class SettingsView(QWidget):
    """
    Settings / Profile view for the logged-in user.

    Currently exposes a Change Password form wired to :class:`AuthController`.
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
        layout.setSpacing(16)

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

        layout.addStretch()

    def _connect_signals(self) -> None:
        self.btnSavePassword.clicked.connect(self._on_save_password_clicked)

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