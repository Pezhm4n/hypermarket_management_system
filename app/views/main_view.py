from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, Optional

import arabic_reshaper
from bidi.algorithm import get_display

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
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
from app.views.inventory_view import InventoryView
from app.views.sales_view import SalesView
from app.views.settings_view import SettingsView
from app.views.users_view import UsersView

logger = logging.getLogger(__name__)


class MatplotlibWidget(QWidget):
    """
    Lightweight wrapper around a Matplotlib FigureCanvas for use in Qt layouts.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        try:
            self._figure = Figure(figsize=(5, 3))
            self._canvas = FigureCanvas(self._figure)
            self._axes = self._figure.add_subplot(111)

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

        # Ensure a professional default window size
        self.setMinimumSize(1280, 800)

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
        # Dashboard page with KPI cards and sales chart
        dashboard_page = QWidget(self.stacked_widget)
        dashboard_layout = QVBoxLayout(dashboard_page)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(16)

        # KPI row
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(16)

        # Today's sales card
        self._kpi_sales_frame = QFrame(dashboard_page)
        self._kpi_sales_frame.setFrameShape(QFrame.Shape.StyledPanel)
        sales_layout = QVBoxLayout(self._kpi_sales_frame)
        sales_layout.setContentsMargins(16, 12, 16, 12)
        sales_layout.setSpacing(4)

        self._kpi_sales_title = QLabel(self._kpi_sales_frame)
        self._kpi_sales_value = QLabel(self._kpi_sales_frame)
        self._kpi_sales_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._kpi_sales_value.setObjectName("KpiValueSales")

        sales_layout.addWidget(self._kpi_sales_title)
        sales_layout.addWidget(self._kpi_sales_value)

        # Orders card
        self._kpi_orders_frame = QFrame(dashboard_page)
        self._kpi_orders_frame.setFrameShape(QFrame.Shape.StyledPanel)
        orders_layout = QVBoxLayout(self._kpi_orders_frame)
        orders_layout.setContentsMargins(16, 12, 16, 12)
        orders_layout.setSpacing(4)

        self._kpi_orders_title = QLabel(self._kpi_orders_frame)
        self._kpi_orders_value = QLabel(self._kpi_orders_frame)
        self._kpi_orders_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._kpi_orders_value.setObjectName("KpiValueOrders")

        orders_layout.addWidget(self._kpi_orders_title)
        orders_layout.addWidget(self._kpi_orders_value)

        kpi_layout.addWidget(self._kpi_sales_frame)
        kpi_layout.addWidget(self._kpi_orders_frame)
        kpi_layout.addStretch()

        dashboard_layout.addLayout(kpi_layout)

        # Sales chart
        self._sales_chart_widget = MatplotlibWidget(dashboard_page)
        dashboard_layout.addWidget(self._sales_chart_widget)

        self._dashboard_page = dashboard_page

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
        self.refresh_dashboard()

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
        self._reports_label.setText(self._translator["main.section.reports"])

        # Dashboard KPI titles
        if hasattr(self, "_kpi_sales_title"):
            self._kpi_sales_title.setText(
                self._translator["dashboard.kpi.today_sales"]
            )
        if hasattr(self, "_kpi_orders_title"):
            self._kpi_orders_title.setText(
                self._translator["dashboard.kpi.open_orders"]
            )

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
            stats = self._sales_controller.get_today_dashboard_stats()
            total_sales = stats.get("total_sales")
            invoice_count = stats.get("invoice_count")

            if total_sales is None:
                total_sales = Decimal("0")
            if invoice_count is None:
                invoice_count = 0

            formatted_total = f"{float(total_sales):,.0f}"

            if hasattr(self, "_kpi_sales_value"):
                self._kpi_sales_value.setText(formatted_total)
            if hasattr(self, "_kpi_orders_value"):
                self._kpi_orders_value.setText(str(int(invoice_count)))

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
                "Dashboard refreshed: total_sales=%s, invoice_count=%s",
                formatted_total,
                invoice_count,
            )
        except Exception as e:
            logger.error("Error in refresh_dashboard: %s", e, exc_info=True)

    def refresh_dashboard_stats(self) -> None:
        """
        Backwards-compatible wrapper for older callers.
        """
        self.refresh_dashboard()

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
            # Cashier: Dashboard + Sales + Inventory
            for key, btn in self._nav_buttons:
                if key not in {"dashboard", "sales", "inventory"}:
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
            # Warehouse: Inventory only
            for key, btn in self._nav_buttons:
                if key != "inventory":
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