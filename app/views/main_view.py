from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, Optional

import arabic_reshaper
from bidi.algorithm import get_display

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from app.controllers.auth_controller import AuthController
from app.controllers.sales_controller import SalesController
from app.core.translation_manager import TranslationManager
from app.models.models import UserAccount
from app.utils import resource_path
from app.views.inventory_view import InventoryView
from app.views.reports_view import ReportsView
from app.views.sales_view import SalesView
from app.views.settings_view import SettingsView
from app.views.users_view import UsersView
from app.views.suppliers_view import SuppliersView
from app.views.components.help_dialog import HelpDialog

logger = logging.getLogger(__name__)


class MatplotlibWidget(QWidget):
    """
    Lightweight wrapper around a Matplotlib FigureCanvas for use in Qt layouts.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        try:
            # Match the application's dark theme background
            self._figure = Figure(figsize=(5, 3), facecolor="#020617")
            self._canvas = FigureCanvas(self._figure)
            self._axes = self._figure.add_subplot(111)
            self._axes.set_facecolor("#020617")

            # Subtle axis styling to avoid a \"boxed\" white chart look
            for spine in self._axes.spines.values():
                spine.set_color("#4b5563")
            self._axes.tick_params(colors="#e5e7eb")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._canvas)
        except Exception as e:
            logger.error("Error initializing MatplotlibWidget: %s", e, exc_info=True)

    def _fix_text(self, text: str) -> str:
        """
        Prepare Arabic/Persian text for correct rendering in Matplotlib.
        """
        try:
            if not text:
                return ""
            reshaped_text = arabic_reshaper.reshape(str(text))
            return get_display(reshaped_text)
        except Exception:
            # Fallback to original text if reshaping fails for any reason
            return str(text)

    def plot_bar(self, labels: list[str], values: list[float], title: str) -> None:
        """
        Render a simple bar chart with the given labels and values.
        """
        try:
            if not hasattr(self, "_axes"):
                return

            self._axes.clear()

            display_labels: list[str] = []
            plot_values: list[float] = []

            if labels and values:
                count = min(len(labels), len(values))
                if count > 0:
                    display_labels = [self._fix_text(str(label)) for label in labels[:count]]
                    plot_values = list(values[:count])
                    x_positions = list(range(count))
                    self._axes.bar(x_positions, plot_values, color="#38bdf8")
                    self._axes.set_xticks(x_positions)
                    self._axes.set_xticklabels(display_labels)

            self._axes.set_title(self._fix_text(title))
            self._axes.set_ylabel(self._fix_text("Sales"))
            self._axes.grid(axis="y", linestyle="--", alpha=0.3)

            self._figure.tight_layout()
            self._canvas.draw_idle()
        except Exception as e:
            logger.error("Error in MatplotlibWidget.plot_bar: %s", e, exc_info=True)


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
        self._current_page_key: str = "sales"
        self._low_stock_click_enabled: bool = False

        # Ensure a professional default window size
        # Slightly wider minimum to give more breathing room to content layouts.
        self.setMinimumSize(1360, 800)

        # Apply application identity (icon + title)
        logo_path = resource_path("app/assets/logo.png")
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))
        base_title = self._translator.get(
            "main.window_title_full",
            self._translator.get("main.window_title", "PeMa Manager"),
        )
        self.setWindowTitle(base_title)

        self._build_ui()
        self._create_module_views()
        self._connect_signals()

        self._translator.language_changed.connect(self._on_language_changed)
        self._apply_translations()
        self.refresh_dashboard()

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
        self.btnSuppliers = QPushButton(self.sidebar)
        self.btnReports = QPushButton(self.sidebar)
        self.btnUsers = QPushButton(self.sidebar)
        self.btnSettings = QPushButton(self.sidebar)

        self._nav_buttons = [
            ("dashboard", self.btnDashboard),
            ("sales", self.btnSales),
            ("inventory", self.btnInventory),
            ("suppliers", self.btnSuppliers),
            ("reports", self.btnReports),
            ("users", self.btnUsers),
            ("settings", self.btnSettings),
        ]

        # Contextual help button (opens help dialog, not a navigation page)
        self.btnHelp = QPushButton(self.sidebar)
        self.btnHelp.setObjectName("SidebarHelpButton")
        # Style like other sidebar navigation buttons (transparent background, hover state)
        self.btnHelp.setProperty("role", "nav")

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        for _, btn in self._nav_buttons:
            btn.setCheckable(True)
            btn.setProperty("role", "nav")
            sidebar_layout.addWidget(btn)
            self._nav_group.addButton(btn)

        # Help button appears below the main navigation
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(self.btnHelp)

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

        # Right side of header: welcome label + logout
        self.lblCurrentUser = QLabel(self.header_bar)
        self.lblCurrentUser.setObjectName("HeaderUserLabel")
        header_layout.addWidget(self.lblCurrentUser)

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
        # Dashboard page with KPI cards and sales chart
        dashboard_page = QWidget(self.stacked_widget)
        dashboard_layout = QVBoxLayout(dashboard_page)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(16)

        # KPI grid
        kpi_layout = QGridLayout()
        kpi_layout.setContentsMargins(0, 0, 0, 0)
        kpi_layout.setSpacing(16)

        # Today's sales card
        self._kpi_sales_frame = QFrame(dashboard_page)
        self._kpi_sales_frame.setObjectName("KpiCard")
        self._kpi_sales_frame.setFrameShape(QFrame.Shape.StyledPanel)
        sales_layout = QVBoxLayout(self._kpi_sales_frame)
        sales_layout.setContentsMargins(16, 12, 16, 12)
        sales_layout.setSpacing(4)

        self._kpi_sales_title = QLabel(self._kpi_sales_frame)
        self._kpi_sales_title.setObjectName("KpiTitle")
        self._kpi_sales_value = QLabel(self._kpi_sales_frame)
        self._kpi_sales_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._kpi_sales_value.setObjectName("KpiValueSales")

        sales_layout.addWidget(self._kpi_sales_title)
        sales_layout.addWidget(self._kpi_sales_value)

        # Orders card
        self._kpi_orders_frame = QFrame(dashboard_page)
        self._kpi_orders_frame.setObjectName("KpiCard")
        self._kpi_orders_frame.setFrameShape(QFrame.Shape.StyledPanel)
        orders_layout = QVBoxLayout(self._kpi_orders_frame)
        orders_layout.setContentsMargins(16, 12, 16, 12)
        orders_layout.setSpacing(4)

        self._kpi_orders_title = QLabel(self._kpi_orders_frame)
        self._kpi_orders_title.setObjectName("KpiTitle")
        self._kpi_orders_value = QLabel(self._kpi_orders_frame)
        self._kpi_orders_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._kpi_orders_value.setObjectName("KpiValueOrders")

        orders_layout.addWidget(self._kpi_orders_title)
        orders_layout.addWidget(self._kpi_orders_value)

        # Profit card
        self._kpi_profit_frame = QFrame(dashboard_page)
        self._kpi_profit_frame.setObjectName("KpiCardProfit")
        self._kpi_profit_frame.setFrameShape(QFrame.Shape.StyledPanel)
        profit_layout = QVBoxLayout(self._kpi_profit_frame)
        profit_layout.setContentsMargins(16, 12, 16, 12)
        profit_layout.setSpacing(4)

        self._kpi_profit_title = QLabel(self._kpi_profit_frame)
        self._kpi_profit_title.setObjectName("KpiTitle")
        self._kpi_profit_value = QLabel(self._kpi_profit_frame)
        self._kpi_profit_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._kpi_profit_value.setObjectName("KpiValueProfit")

        profit_layout.addWidget(self._kpi_profit_title)
        profit_layout.addWidget(self._kpi_profit_value)

        # Low stock card
        self._kpi_low_stock_frame = QFrame(dashboard_page)
        self._kpi_low_stock_frame.setObjectName("KpiCardLowStock")
        self._kpi_low_stock_frame.setFrameShape(QFrame.Shape.StyledPanel)
        low_stock_layout = QVBoxLayout(self._kpi_low_stock_frame)
        low_stock_layout.setContentsMargins(16, 12, 16, 12)
        low_stock_layout.setSpacing(4)

        self._kpi_low_stock_title = QLabel(self._kpi_low_stock_frame)
        self._kpi_low_stock_title.setObjectName("KpiTitle")
        self._kpi_low_stock_value = QLabel(self._kpi_low_stock_frame)
        self._kpi_low_stock_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._kpi_low_stock_value.setObjectName("KpiValueLowStock")

        low_stock_layout.addWidget(self._kpi_low_stock_title)
        low_stock_layout.addWidget(self._kpi_low_stock_value)

        # Make the low stock card clickable (handled in _on_low_stock_card_clicked)
        self._kpi_low_stock_frame.setCursor(Qt.CursorShape.ArrowCursor)
        self._kpi_low_stock_frame.mousePressEvent = (  # type: ignore[assignment]
            self._on_low_stock_card_clicked
        )

        # Arrange KPI cards in a 2x2 grid
        kpi_layout.addWidget(self._kpi_sales_frame, 0, 0)
        kpi_layout.addWidget(self._kpi_orders_frame, 0, 1)
        kpi_layout.addWidget(self._kpi_profit_frame, 1, 0)
        kpi_layout.addWidget(self._kpi_low_stock_frame, 1, 1)
        kpi_layout.setColumnStretch(0, 1)
        kpi_layout.setColumnStretch(1, 1)

        dashboard_layout.addLayout(kpi_layout)

        # Sales chart
        self._sales_chart_widget = MatplotlibWidget(dashboard_page)
        dashboard_layout.addWidget(self._sales_chart_widget, stretch=1)

        # Copyright footer on dashboard
        self._dashboard_footer = QLabel(dashboard_page)
        self._dashboard_footer.setObjectName("DashboardFooterLabel")
        self._dashboard_footer.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        dashboard_layout.addWidget(self._dashboard_footer)

        self._dashboard_page = dashboard_page

        # Sales / Inventory / Suppliers/ Reports / Settings modules
        self.sales_view = SalesView(self._translator, parent=self.stacked_widget)
        self.inventory_view = InventoryView(
            self._translator,
            parent=self.stacked_widget,
        )
        self.suppliers_view = SuppliersView(self._translator, parent=self.stacked_widget)
        self.reports_view = ReportsView(
            translation_manager=self._translator,
            parent=self.stacked_widget,
        )
        self.settings_view = SettingsView(
            auth_controller=self._auth_controller,
            translation_manager=self._translator,
            parent=self.stacked_widget,
        )


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
        self._page_indices["reports"] = self.stacked_widget.addWidget(self.reports_view)
        self._page_indices["users"] = self.stacked_widget.addWidget(self.users_view)
        self._page_indices["settings"] = self.stacked_widget.addWidget(
            self.settings_view
        )
        self._page_indices["suppliers"] = self.stacked_widget.addWidget(self.suppliers_view)

        # Default page
        self._switch_page("sales")

    def _connect_signals(self) -> None:
        # Navigation buttons
        for key, btn in self._nav_buttons:
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))

        # Help dialog
        self.btnHelp.clicked.connect(self._on_help_clicked)

        # Logout
        self.btnLogout.clicked.connect(self._on_logout_clicked)

    # ------------------------------------------------------------------ #
    # Translation helpers
    # ------------------------------------------------------------------ #
    def _on_language_changed(self, language: str) -> None:
        _ = language
        self._apply_translations()
        self.refresh_dashboard()

    def _apply_translations(self) -> None:
        """
        Apply localized texts to sidebar, header and static pages.
        """
        # Window title and app title
        base_title = self._translator.get(
            "main.window_title_full",
            self._translator.get("main.window_title", "PeMa Manager"),
        )
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
            "suppliers": "sidebar.suppliers",
            "reports": "sidebar.reports",
            "users": "sidebar.users",
            "settings": "sidebar.settings",
        }
        for key, btn in self._nav_buttons:
            btn.setText(self._translator[text_keys[key]])

        # Help button label
        self.btnHelp.setText(self._translator.get("sidebar.help", "Help"))

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

        # Dashboard KPI titles
        if hasattr(self, "_kpi_sales_title"):
            self._kpi_sales_title.setText(
                self._translator["dashboard.kpi.today_sales"]
            )
        if hasattr(self, "_kpi_orders_title"):
            self._kpi_orders_title.setText(
                self._translator["dashboard.kpi.open_orders"]
            )
        if hasattr(self, "_kpi_profit_title"):
            self._kpi_profit_title.setText(
                self._translator.get("dashboard.kpi.today_profit", "Today's Profit")
            )
        if hasattr(self, "_kpi_low_stock_title"):
            self._kpi_low_stock_title.setText(
                self._translator.get(
                    "dashboard.kpi.low_stock",
                    "Low stock items",
                )
            )

        if hasattr(self, "_dashboard_footer"):
            self._dashboard_footer.setText(
                self._translator.get(
                    "app.footer.copyright",
                    "© 2026 All rights reserved.",
                )
            )

        # Update header title for current page
        current_key = self._current_page_key
        self._update_header_for_page(current_key)

    # ------------------------------------------------------------------ #
    # Navigation / dialogs
    # ------------------------------------------------------------------ #
    def _on_help_clicked(self) -> None:
        """Open the contextual help dialog with language-aware content."""
        try:
            dialog = HelpDialog(translation_manager=self._translator, parent=self)
            dialog.exec()
        except Exception as exc:
            logger.error("Error opening Help dialog: %s", exc, exc_info=True)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )

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
            self.refresh_dashboard()
        elif page_key == "sales":
            try:
                self.sales_view.ensure_active_shift()
            except Exception as e:
                logger.error(
                    "Error ensuring active shift when switching to Sales page: %s",
                    e,
                    exc_info=True,
                )
        elif page_key == "inventory":
            try:
                if hasattr(self, "inventory_view") and hasattr(
                    self.inventory_view, "refresh"
                ):
                    self.inventory_view.refresh()
            except Exception as e:
                logger.error(
                    "Error refreshing InventoryView when switching page: %s",
                    e,
                    exc_info=True,
                )
        elif page_key == "reports":
            try:
                if hasattr(self, "reports_view") and hasattr(
                    self.reports_view, "_generate_report"
                ):
                    self.reports_view._generate_report()
            except Exception as e:
                logger.error(
                    "Error refreshing ReportsView when switching page: %s",
                    e,
                    exc_info=True,
                )

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
    def refresh_dashboard(self) -> None:
        """
        Refresh dashboard KPI cards and the 7-day sales chart.
        """
        try:
            stats = self._sales_controller.get_dashboard_stats()
            total_sales = stats.get("total_sales")
            transaction_count = stats.get("transaction_count")
            total_profit = stats.get("total_profit")
            low_stock_count = stats.get("low_stock_count")

            if total_sales is None:
                total_sales = Decimal("0")
            if transaction_count is None:
                transaction_count = 0
            if total_profit is None:
                total_profit = Decimal("0")
            if low_stock_count is None:
                low_stock_count = 0

            formatted_sales = f"{float(total_sales):,.0f}"
            formatted_profit = f"{float(total_profit):,.0f}"

            if hasattr(self, "_kpi_sales_value"):
                self._kpi_sales_value.setText(formatted_sales)
            if hasattr(self, "_kpi_orders_value"):
                self._kpi_orders_value.setText(str(int(transaction_count)))
            if hasattr(self, "_kpi_profit_value"):
                self._kpi_profit_value.setText(formatted_profit)
            if hasattr(self, "_kpi_low_stock_value"):
                self._kpi_low_stock_value.setText(str(int(low_stock_count)))

            # Enable or disable click behavior for low stock card
            self._low_stock_click_enabled = bool(low_stock_count > 0)
            if hasattr(self, "_kpi_low_stock_frame"):
                cursor = (
                    Qt.CursorShape.PointingHandCursor
                    if self._low_stock_click_enabled
                    else Qt.CursorShape.ArrowCursor
                )
                self._kpi_low_stock_frame.setCursor(cursor)

            # Update last 7 days sales chart
            series = self._sales_controller.get_last_7_days_sales_series()
            labels = series.get("labels", [])
            totals = series.get("totals", [])

            numeric_totals: list[float] = []
            for value in totals:
                try:
                    numeric_totals.append(float(value))
                except Exception:
                    numeric_totals.append(0.0)

            if hasattr(self, "_sales_chart_widget"):
                chart_title = self._translator["dashboard.chart_title"]
                self._sales_chart_widget.plot_bar(
                    labels,
                    numeric_totals,
                    chart_title,
                )

            logger.info(
                "Dashboard refreshed: total_sales=%s, transactions=%s, profit=%s, low_stock=%s",
                formatted_sales,
                transaction_count,
                formatted_profit,
                low_stock_count,
            )
        except Exception as e:
            logger.error("Error in refresh_dashboard: %s", e, exc_info=True)

    def refresh_dashboard_stats(self) -> None:
        """
        Backwards-compatible wrapper for older callers.
        """
        self.refresh_dashboard()

    def _on_low_stock_card_clicked(self, event) -> None:  # type: ignore[override]
        """
        Navigate to the Inventory view when the low stock KPI card is clicked.
        Only active when low_stock_count > 0.
        """
        try:
            _ = event
            if not getattr(self, "_low_stock_click_enabled", False):
                return

            self._switch_page("inventory")
        except Exception as e:
            logger.error("Error in _on_low_stock_card_clicked: %s", e, exc_info=True)

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

        # Role-based access control
        role_title = getattr(user, "Role", None)
        normalized_role = (role_title or "").strip().lower()
        logger.info(
            "Applying RBAC for user '%s' with role '%s'.",
            user.Username,
            role_title,
        )

        # Default: show all navigation
        for _, btn in self._nav_buttons:
            btn.setEnabled(True)
            btn.setVisible(True)

        # Users module is admin-only
        if normalized_role != "admin":
            self.btnUsers.setVisible(False)

        # Role-specific visibility
        if normalized_role == "cashier":
            # Cashier: Dashboard + Sales + Inventory + Settings
            allowed_keys = {"dashboard", "sales", "inventory", "settings"}
            for key, btn in self._nav_buttons:
                if key not in allowed_keys:
                    btn.setVisible(False)
                    btn.setEnabled(False)
            # Inventory is read-only for cashiers
            try:
                if hasattr(self, "inventory_view") and hasattr(
                    self.inventory_view, "set_read_only"
                ):
                    self.inventory_view.set_read_only(True)
            except Exception as e:
                logger.error("Error applying read-only mode for InventoryView: %s", e, exc_info=True)
            self._switch_page("sales")
        elif normalized_role == "warehouse":
            # Warehouse: Inventory + Settings
            allowed_keys = {"inventory", "settings"}
            for key, btn in self._nav_buttons:
                if key not in allowed_keys:
                    btn.setVisible(False)
                    btn.setEnabled(False)
            try:
                if hasattr(self, "inventory_view") and hasattr(
                    self.inventory_view, "set_read_only"
                ):
                    self.inventory_view.set_read_only(False)
            except Exception as e:
                logger.error("Error applying read/write mode for InventoryView: %s", e, exc_info=True)
            self._switch_page("inventory")
        else:
            # Admin or unknown: full access; default to Sales
            try:
                if hasattr(self, "inventory_view") and hasattr(
                    self.inventory_view, "set_read_only"
                ):
                    self.inventory_view.set_read_only(False)
            except Exception as e:
                logger.error("Error applying admin mode for InventoryView: %s", e, exc_info=True)
            self._switch_page("sales")

        self._apply_translations()
        self.refresh_dashboard()

    # ------------------------------------------------------------------ #
    # Window / lifecycle
    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:  # type: ignore[override]
        """
        Intercept window close to optionally close an active shift.
        """
        try:
            if hasattr(self, "sales_view") and getattr(
                self.sales_view, "has_active_shift", None
            ):
                if self.sales_view.has_active_shift():
                    reply = QMessageBox.question(
                        self,
                        self._translator["shift.close_confirm_title"],
                        self._translator["shift.close_confirm_body"],
                        QMessageBox.StandardButton.Yes
                        | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        try:
                            if getattr(self.sales_view, "close_shift", None):
                                self.sales_view.close_shift()
                        except Exception as inner_exc:
                            logger.error(
                                "Error while closing shift during app exit: %s",
                                inner_exc,
                                exc_info=True,
                            )
            event.accept()
        except Exception as e:
            logger.error("Error in MainView.closeEvent: %s", e, exc_info=True)
            event.accept()

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_logout_clicked(self) -> None:
        """
        Emit a signal to notify the application that the user requested logout.
        """
        self.logout_requested.emit()