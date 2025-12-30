from __future__ import annotations

from typing import Optional

from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from app.controllers.auth_controller import AuthController
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
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._auth_controller = auth_controller

        uic.loadUi("app/views/ui/login.ui", self)

        self.lblError.setText("")
        self.btnLogin.clicked.connect(self._on_login_clicked)

    def _on_login_clicked(self) -> None:
        username = self.txtUsername.text().strip()
        password = self.txtPassword.text()

        if not username or not password:
            self._show_error("Please enter both username and password.")
            return

        user: Optional[UserAccount] = self._auth_controller.login(username, password)
        if user is None:
            self._show_error("Invalid username or password.")
            return

        # Clear error and notify listeners.
        self._show_error("")
        self.login_success.emit(user)

    def _show_error(self, message: str) -> None:
        self.lblError.setText(message or "")