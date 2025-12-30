from __future__ import annotations

from typing import Optional

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow

from app.models.models import UserAccount
from app.views.inventory_view import InventoryView
from app.views.sales_view import SalesView


class MainView(QMainWindow):
    """
    Main application window for HMS.

    Loads its layout from app/views/ui/main_window.ui and wires the sidebar
    buttons to switch between core module views within the central
    QStackedWidget.
    """

    def __init__(
        self,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        super().__init__(parent)

        uic.loadUi("app/views/ui/main_window.ui", self)

        self.current_user: Optional[UserAccount] = None

        # Instantiate module views
        self.sales_view = SalesView(self)
        self.inventory_view = InventoryView(self)

        # Replace placeholder pages with real module views
        self._install_module_views()

        # Wire sidebar actions
        self._connect_sidebar()

    def _install_module_views(self) -> None:
        """
        Remove placeholder label pages (Phase 2) and install the real
        Sales and Inventory views as pages in the stacked widget.
        """
        # Remove old Sales page if present
        sales_page = getattr(self, "pageSales", None)
        if sales_page is not None:
            index = self.stackedWidget.indexOf(sales_page)
            if index != -1:
                self.stackedWidget.removeWidget(sales_page)
            sales_page.deleteLater()

        # Remove old Inventory page if present
        inventory_page = getattr(self, "pageInventory", None)
        if inventory_page is not None:
            index = self.stackedWidget.indexOf(inventory_page)
            if index != -1:
                self.stackedWidget.removeWidget(inventory_page)
            inventory_page.deleteLater()

        # Install new views as standalone pages
        self.stackedWidget.addWidget(self.sales_view)
        self.stackedWidget.addWidget(self.inventory_view)

        # Cache indices so sidebar actions remain robust even if the order
        # of pages changes in the future.
        self._sales_index = self.stackedWidget.indexOf(self.sales_view)
        self._inventory_index = self.stackedWidget.indexOf(self.inventory_view)

        # Reports and Users still use the placeholder pages from the .ui file
        self._reports_index = self.stackedWidget.indexOf(self.pageReports)
        self._users_index = self.stackedWidget.indexOf(self.pageUsers)

        # Default to Sales module on load, if available
        if self._sales_index != -1:
            self._set_page_index(self._sales_index)

    def _connect_sidebar(self) -> None:
        self.btnSales.clicked.connect(
            lambda: self._set_page_index(self._sales_index)
        )
        self.btnInventory.clicked.connect(
            lambda: self._set_page_index(self._inventory_index)
        )
        self.btnReports.clicked.connect(
            lambda: self._set_page_index(self._reports_index)
        )
        self.btnUsers.clicked.connect(
            lambda: self._set_page_index(self._users_index)
        )

    def _set_page_index(self, index: int) -> None:
        if self.stackedWidget is not None and index != -1:
            self.stackedWidget.setCurrentIndex(index)

    def set_logged_in_user(self, user: UserAccount) -> None:
        """
        Store the authenticated user and update any user-related UI chrome.
        """
        self.current_user = user
        self.setWindowTitle(f"Hypermarket Management System - {user.Username}")