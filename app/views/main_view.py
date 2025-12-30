from __future__ import annotations

from typing import Optional

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow

from app.models.models import UserAccount


class MainView(QMainWindow):
    """
    Main application window for HMS.

    Loads its layout from app/views/ui/main_window.ui and wires the sidebar
    buttons to switch pages within the central QStackedWidget.
    """

    def __init__(
        self,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        super().__init__(parent)

        uic.loadUi("app/views/ui/main_window.ui", self)

        self.current_user: Optional[UserAccount] = None

        self._connect_sidebar()

    def _connect_sidebar(self) -> None:
        self.btnSales.clicked.connect(lambda: self._set_page_index(0))
        self.btnInventory.clicked.connect(lambda: self._set_page_index(1))
        self.btnReports.clicked.connect(lambda: self._set_page_index(2))
        self.btnUsers.clicked.connect(lambda: self._set_page_index(3))

    def _set_page_index(self, index: int) -> None:
        if self.stackedWidget is not None:
            self.stackedWidget.setCurrentIndex(index)

    def set_logged_in_user(self, user: UserAccount) -> None:
        """
        Store the authenticated user and update any user-related UI chrome.
        """
        self.current_user = user
        self.setWindowTitle(f"Hypermarket Management System - {user.Username}")