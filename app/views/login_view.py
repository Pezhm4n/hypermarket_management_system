from __future__ import annotations

from typing import Optional

from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from app.controllers.auth_controller import AuthController
from app.core.translation_manager import TranslationManager
from app.models.models import UserAccount


class LoginView(QWidget):
    """
    Login screen for HMS.

    Loads its layout from app/views/ui/login.ui and delegates authentication
    to AuthController. On successful login, emits login_success with the
    authenticated UserAccount instance.
    """

    login_success = pyqtSignal(object)

    def __init__(
        self,
        auth_controller: AuthController,
        translation_manager: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._auth_controller = auth_controller
        self._translator = translation_manager

        uic.loadUi("app/views/ui/login.ui", self)

        # Ensure error label uses a predictable object name for styling.
        self.lblError.setObjectName("LoginErrorLabel")
        self.lblError.setText("")
        self.btnLogin.clicked.connect(self._on_login_clicked)

        # React to language changes and apply initial texts.
        self._translator.language_changed.connect(self._on_language_changed)
        self._apply_translations()

    def _on_language_changed(self, language: str) -> None:
        _ = language  # required by signal; not used directly
        self._apply_translations()

    def _apply_translations(self) -> None:
        """
        Apply localized texts to all visible widgets on the login form.
        """
        self.setWindowTitle(self._translator["login.window_title"])
        self.lblTitle.setText(self._translator["login.heading"])
        self.lblUsername.setText(self._translator["login.username_label"])
        self.txtUsername.setPlaceholderText(
            self._translator["login.username_placeholder"]
        )
        self.lblPassword.setText(self._translator["login.password_label"])
        self.txtPassword.setPlaceholderText(
            self._translator["login.password_placeholder"]
        )
        self.btnLogin.setText(self._translator["login.button"])

    def _on_login_clicked(self) -> None:
        username = self.txtUsername.text().strip()
        password = self.txtPassword.text()

        if not username or not password:
            self._show_error(self._translator["login.error.empty"])
            return

        user: Optional[UserAccount] = self._auth_controller.login(username, password)
        if user is None:
            self._show_error(self._translator["login.error.invalid"])
            return

        # Clear error and notify listeners.
        self._show_error("")
        self.login_success.emit(user)

    def _show_error(self, message: str) -> None:
        self.lblError.setText(message or "")