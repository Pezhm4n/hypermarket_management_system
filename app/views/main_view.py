from __future__ import annotations

import logging
from typing import Dict, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.controllers.auth_controller import AuthController
from app.controllers.sales_controller import SalesController
from app.core.translation_manager import TranslationManager
from app.models.models import UserAccount
from app.views.inventory_view import InventoryView
from app.views.sales_view import SalesView
from app.views.settings_view import SettingsView
from app.views.users_view import UsersView

logger = logging.getLogger(__name__)


class MainView(QMainWindow):
    """
    Main application window for HMS.

    Implements a modern dashboard layout with:

    * A left-hand sidebar for navigation.
    * A content area with a header bar and module pages (Sales, Inventory,
      Reports, Users, Settings).
    * Bilingual FA/EN support via :class:`TranslationManager`.
    """

    logout_requested = pyqtSignal()

    def __init__(
        self,
        auth_controller: AuthController,
        translation_manager: TranslationManager,
        parent: Optional[QMainWindow] = None,
    ) -> None:
        super().__init__(parent)

        self._auth_controller = auth_controller
        self._translator = translation_manager
        self._sales_controller = SalesController()

        self.current_user: Optional[UserAccount] = None

        self._page_indices: Dict[str, int] = {}

        # Ensure a professional default window size
        self.setMinimumSize(1280, 800)

        self._build_ui()
        self._create_module_views()
        self._connect_signals()

        self._translator.language_changed.connect(self._on_language_changed)
        self._apply_translations()
        self.refresh_dashboard_stats()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """
        Build the main dashboard layout using Qt layouts.

        The layout is responsive and avoids fixed geometry usage so the window
        behaves well when resized.
        """
        central = QWidget(self)
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar
        self.sidebar = QFrame(central)
        self.sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)
        sidebar_layout.setSpacing(12)

        self.lblAppTitle = QLabel(self.sidebar)
        self.lblAppTitle.setObjectName("SidebarTitle")
        self.lblAppTitle.setWordWrap(True)
        sidebar_layout.addWidget(self.lblAppTitle)

        sidebar_layout.addSpacing(12)

        # Navigation buttons
        self.btnDashboard = QPushButton(self.sidebar)
        self.btnSales = QPushButton(self.sidebar)
        self.btnInventory = QPushButton(self.sidebar)
        self.btnReports = QPushButton(self.sidebar)
        self.btnUsers = QPushButton(self.sidebar)
        self.btnSettings = QPushButton(self.sidebar)

        self._nav_buttons = [
            ("dashboard", self.btnDashboard),
            ("sales", self.btnSales),
            ("inventory", self.btnInventory),
            ("reports", self.btnReports),
            ("users", self.btnUsers),
            ("settings", self.btnSettings),
        ]

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        for _, btn in self._nav_buttons:
            btn.setCheckable(True)
            btn.setProperty("role", "nav")
            sidebar_layout.addWidget(btn)
            self._nav_group.addButton(btn)

        # Sidebar now only contains navigation
        sidebar_layout.addStretch()

        root_layout.addWidget(self.sidebar)

        # Content area
        self.content = QWidget(central)
        self.content.setObjectName("ContentArea")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)

        # Header bar
        self.header_bar = QFrame(self.content)
        self.header_bar.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(12)

        self.lblSectionTitle = QLabel(self.header_bar)
        self.lblSectionTitle.setObjectName("HeaderTitle")

        self.lblSectionSubtitle = QLabel(self.header_bar)
        self.lblSectionSubtitle.setObjectName("HeaderSubtitle")

        header_text_layout = QVBoxLayout()
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.setSpacing(2)
        header_text_layout.addWidget(self.lblSectionTitle)
        header_text_layout.addWidget(self.lblSectionSubtitle)

        header_layout.addLayout(header_text_layout)
        header_layout.addStretch()

        # Right side of header: welcome label + language toggles + logout
        self.lblCurrentUser = QLabel(self.header_bar)
        self.lblCurrentUser.setObjectName("HeaderUserLabel")
        header_layout.addWidget(self.lblCurrentUser)

        # Language buttons
        self.btnLanguageEn = QPushButton(self.header_bar)
        self.btnLanguageEn.setProperty("role", "language")

        self.btnLanguageFa = QPushButton(self.header_bar)
        self.btnLanguageFa.setProperty("role", "language")

        self._lang_group = QButtonGroup(self)
        self._lang_group.setExclusive(True)
        self._lang_group.addButton(self.btnLanguageEn)
        self._lang_group.addButton(self.btnLanguageFa)

        header_layout.addWidget(self.btnLanguageEn)
        header_layout.addWidget(self.btnLanguageFa)

        # Logout button
        self.btnLogout = QPushButton(self.header_bar)
        self.btnLogout.setProperty("role", "logout")
        header_layout.addWidget(self.btnLogout)

        content_layout.addWidget(self.header_bar)

        # Stacked widget for module pages
        self.stacked_widget = QStackedWidget(self.content)
        self.stacked_widget.setObjectName("ContentStack")
        content_layout.addWidget(self.stacked_widget)

        root_layout.addWidget(self.content, stretch=1)

    def _create_module_views(self) -> None:
        """
        Instantiate module views and add them as pages in the stacked widget.
        """
        # Dashboard page (simple stats placeholder)
        dashboard_page = QWidget(self.stacked_widget)
        dashboard_layout = QVBoxLayout(dashboard_page)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(0)

        lbl_dashboard = QLabel(dashboard_page)
        lbl_dashboard.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dashboard_layout.addWidget(lbl_dashboard)
        self._dashboard_label = lbl_dashboard  # used for dashboard stats

        # Sales / Inventory modules
        self.sales_view = SalesView(self._translator, parent=self.stacked_widget)
        self.inventory_view = InventoryView(
            self._translator,
            parent=self.stacked_widget,
        )
        self.settings_view = SettingsView(
            auth_controller=self._auth_controller,
            translation_manager=self._translator,
            parent=self.stacked_widget,
        )

        reports_page = QWidget(self.stacked_widget)
        reports_layout = QVBoxLayout(reports_page)
        reports_layout.setContentsMargins(0, 0, 0, 0)
        reports_layout.setSpacing(0)
        self._reports_label = QLabel(reports_page)
        self._reports_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reports_layout.addWidget(self._reports_label)

        # Users module view
        self.users_view = UsersView(
            translation_manager=self._translator,
            parent=self.stacked_widget,
        )

        # Add pages to stacked widget and record indices
        self._page_indices["dashboard"] = self.stacked_widget.addWidget(
            dashboard_page
        )
        self._page_indices["sales"] = self.stacked_widget.addWidget(self.sales_view)
        self._page_indices["inventory"] = self.stacked_widget.addWidget(
            self.inventory_view
        )
        self._page_indices["reports"] = self.stacked_widget.addWidget(reports_page)
        self._page_indices["users"] = self.stacked_widget.addWidget(self.users_view)
        self._page_indices["settings"] = self.stacked_widget.addWidget(
            self.settings_view
        )

        # Default page
        self._switch_page("sales")

    def _connect_signals(self) -> None:
        # Navigation buttons
        for key, btn in self._nav_buttons:
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))

        # Language switching
        self.btnLanguageEn.clicked.connect(
            lambda: self._translator.set_language("en")
        )
        self.btnLanguageFa.clicked.connect(
            lambda: self._translator.set_language("fa")
        )

        # Logout
        self.btnLogout.clicked.connect(self._on_logout_clicked)

    # ------------------------------------------------------------------ #
    # Translation helpers
    # ------------------------------------------------------------------ #
    def _on_language_changed(self, language: str) -> None:
        _ = language
        self._apply_translations()
        self.refresh_dashboard_stats()

    def _apply_translations(self) -> None:
        """
        Apply localized texts to sidebar, header and static pages.
        """
        # Window title and app title
        base_title = self._translator["main.window_title"]
        if self.current_user is not None:
            self.setWindowTitle(f"{base_title} - {self.current_user.Username}")
        else:
            self.setWindowTitle(base_title)

        self.lblAppTitle.setText(self._translator["app.title"])

        # Sidebar buttons
        text_keys = {
            "dashboard": "sidebar.dashboard",
            "sales": "sidebar.sales",
            "inventory": "sidebar.inventory",
            "reports": "sidebar.reports",
            "users": "sidebar.users",
            "settings": "sidebar.settings",
        }
        for key, btn in self._nav_buttons:
            btn.setText(self._translator[text_keys[key]])

        self.btnLanguageEn.setText(self._translator["sidebar.language.en"])
        self.btnLanguageFa.setText(self._translator["sidebar.language.fa"])
        self.btnLogout.setText(self._translator["sidebar.logout"])

        # Header
        self.lblSectionSubtitle.setText(
            self._translator["main.header.subtitle"]
        )
        if self.current_user is not None:
            welcome = self._translator["main.header.welcome"]
            self.lblCurrentUser.setText(f"{welcome} {self.current_user.Username}")
        else:
            self.lblCurrentUser.setText("")

        # Static page labels
        self._dashboard_label.setText(self._translator["main.section.dashboard"])
        self._reports_label.setText(self._translator["main.section.reports"])

        # Ensure language toggle reflects active language
        if self._translator.language == "fa":
            self.btnLanguageFa.setChecked(True)
            self.btnLanguageEn.setChecked(False)
        else:
            self.btnLanguageEn.setChecked(True)
            self.btnLanguageFa.setChecked(False)

        # Update header title for current page
        current_key = self._current_page_key
        self._update_header_for_page(current_key)

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #
    def _switch_page(self, page_key: str) -> None:
        """
        Switch the central stacked widget to the page identified by *page_key*.
        """
        index = self._page_indices.get(page_key, -1)
        if index == -1:
            return

        self._current_page_key = page_key
        self.stacked_widget.setCurrentIndex(index)

        # Ensure corresponding nav button appears checked
        for key, btn in self._nav_buttons:
            btn.setChecked(key == page_key)

        self._update_header_for_page(page_key)

        if page_key == "dashboard":
            self.refresh_dashboard_stats()

    def _update_header_for_page(self, page_key: str) -> None:
        section_keys = {
            "dashboard": "main.section.dashboard",
            "sales": "main.section.sales",
            "inventory": "main.section.inventory",
            "reports": "main.section.reports",
            "users": "main.section.users",
            "settings": "main.section.settings",
        }
        key = section_keys.get(page_key)
        if key is not None:
            self.lblSectionTitle.setText(self._translator[key])

    # ------------------------------------------------------------------ #
    # Dashboard stats
    # ------------------------------------------------------------------ #
    def refresh_dashboard_stats(self) -> None:
        """
        Refresh top-level dashboard statistics (today's sales and invoices).
        """
        try:
            stats = self._sales_controller.get_today_dashboard_stats()
            total_sales = stats.get("total_sales")
            invoice_count = stats.get("invoice_count")

            if total_sales is None or invoice_count is None:
                return

            formatted_total = f"{float(total_sales):,.0f}"
            title = self._translator["main.section.dashboard"]

            self._dashboard_label.setText(
                f"{title}\n\n"
                f"Total Sales Today: {formatted_total}\n"
                f"Invoices Today: {invoice_count}"
            )

            logger.info(
                "Dashboard stats updated: total_sales=%s, invoice_count=%s",
                formatted_total,
                invoice_count,
            )
        except Exception as e:
            logger.error("Error in refresh_dashboard_stats: %s", e, exc_info=True)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def set_logged_in_user(self, user: UserAccount) -> None:
        """
        Store the authenticated user and update any user-related UI chrome.
        """
        self.current_user = user
        self.sales_view.set_current_user(user)
        self.settings_view.set_current_user(user)
        self._apply_translations()
        self.refresh_dashboard_stats()

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_logout_clicked(self) -> None:
        """
        Emit a signal to notify the application that the user requested logout.
        """
        self.logout_requested.emit()