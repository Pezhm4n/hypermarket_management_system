from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

import arabic_reshaper
from bidi.algorithm import get_display

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QDateEdit,
    QMessageBox,
)

from matplotlib import rcParams
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from app.controllers.sales_controller import SalesController
from app.core.translation_manager import TranslationManager
from app.database import SessionLocal
from app.models.models import Customer, Invoice

logger = logging.getLogger(__name__)


@dataclass
class InvoiceRow:
    inv_id: int
    inv_date: datetime
    customer_name: str
    total_amount: Decimal
    discount: Decimal


class ReportsChart(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._figure = Figure(figsize=(5, 3))
        self._canvas = FigureCanvas(self._figure)
        self._axes = self._figure.add_subplot(111)

        try:
            rcParams["font.family"] = "sans-serif"
            rcParams["font.sans-serif"] = [
                "Tahoma",
                "Segoe UI",
                "Arial",
                "DejaVu Sans",
            ]
        except Exception as exc:
            logger.error(
                "Error configuring Matplotlib font for ReportsChart: %s",
                exc,
                exc_info=True,
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

    def plot_daily_sales(
        self,
        labels: List[str],
        values: List[Decimal],
        title: Optional[str] = None,
        y_label: Optional[str] = None,
    ) -> None:
        try:
            self._axes.clear()

            float_values = [float(v or 0) for v in values]
            x_positions = list(range(len(labels)))

            if labels and float_values:
                self._axes.bar(x_positions, float_values, color="#38bdf8")
                self._axes.set_xticks(x_positions)
                self._axes.set_xticklabels(labels, rotation=45, ha="right")

            self._axes.set_ylabel(y_label or "Sales")
            if title:
                self._axes.set_title(title)

            self._axes.grid(axis="y", linestyle="--", alpha=0.3)

            self._figure.tight_layout()
            self._canvas.draw_idle()
        except Exception as exc:
            logger.error("Error plotting daily sales chart: %s", exc, exc_info=True)


class ReportsView(QWidget):
    """
    Advanced reports view showing aggregated sales metrics, daily chart,
    and invoice list for a selected date range.
    """

    def __init__(
        self,
        translation_manager: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translation_manager
        self._sales_controller = SalesController()

        self._build_ui()
        self._connect_signals()
        self._translator.language_changed.connect(self._on_language_changed)
        self._apply_translations()

        self._load_default_range()
        self._generate_report()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # Filters
        filters_box = QGroupBox(self)
        filters_layout = QHBoxLayout(filters_box)
        filters_layout.setContentsMargins(12, 8, 12, 8)
        filters_layout.setSpacing(12)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        self.date_from = QDateEdit(self)
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")

        self.date_to = QDateEdit(self)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")

        self.btnGenerate = QPushButton(self)

        form.addRow(QLabel(self), self.date_from)  # labels set in _apply_translations
        form.addRow(QLabel(self), self.date_to)

        filters_layout.addLayout(form)
        filters_layout.addStretch()
        filters_layout.addWidget(self.btnGenerate)

        root_layout.addWidget(filters_box)

        # Metrics
        metrics_frame = QFrame(self)
        metrics_layout = QHBoxLayout(metrics_frame)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(12)

        self._card_total_sales = self._create_metric_card(metrics_layout)
        self._card_total_profit = self._create_metric_card(metrics_layout)
        self._card_tx_count = self._create_metric_card(metrics_layout)

        metrics_layout.addStretch()
        root_layout.addWidget(metrics_frame)

        # Chart + table
        center_frame = QFrame(self)
        center_layout = QVBoxLayout(center_frame)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(12)

        self.chart_widget = ReportsChart(center_frame)
        center_layout.addWidget(self.chart_widget)

        # Table + export
        table_container = QFrame(center_frame)
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)

        self.tblInvoices = QTableWidget(table_container)
        self.tblInvoices.setColumnCount(5)
        self.tblInvoices.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tblInvoices.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.tblInvoices.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        header = self.tblInvoices.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)

        self.btnExport = QPushButton(table_container)

        table_layout.addWidget(self.tblInvoices)
        table_layout.addWidget(self.btnExport, alignment=Qt.AlignmentFlag.AlignRight)

        center_layout.addWidget(table_container)

        root_layout.addWidget(center_frame, stretch=1)

    def _create_metric_card(self, parent_layout: QHBoxLayout) -> dict:
        card = QFrame(self)
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        title = QLabel(card)
        value = QLabel(card)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title)
        layout.addWidget(value)

        parent_layout.addWidget(card)
        return {"frame": card, "title": title, "value": value}

    def _reshape_text(self, text: str) -> str:
        try:
            if not text:
                return ""
            reshaped_text = arabic_reshaper.reshape(str(text))
            return get_display(reshaped_text)
        except Exception:
            return str(text)

    # ------------------------------------------------------------------ #
    # Translations
    # ------------------------------------------------------------------ #
    def _on_language_changed(self, language: str) -> None:
        _ = language
        self._apply_translations()
        self._generate_report()

    def _apply_translations(self) -> None:
        try:
            self.setWindowTitle(self._translator.get("main.section.reports", "Reports"))

            # Filter labels
            filters_box = self.findChild(QGroupBox)
            if filters_box is not None:
                filters_box.setTitle(
                    self._translator.get("reports.filters.title", "Filters")
                )

            # QFormLayout labels
            if isinstance(self.layout().itemAt(0).widget(), QGroupBox):
                filters_box = self.layout().itemAt(0).widget()
                form_layout = filters_box.layout().itemAt(0).layout()
                if isinstance(form_layout, QFormLayout):
                    lbl_from = form_layout.itemAt(0, QFormLayout.ItemRole.LabelRole).widget()
                    lbl_to = form_layout.itemAt(1, QFormLayout.ItemRole.LabelRole).widget()
                    if isinstance(lbl_from, QLabel):
                        lbl_from.setText(
                            self._translator.get("reports.filters.from_date", "From date")
                        )
                    if isinstance(lbl_to, QLabel):
                        lbl_to.setText(
                            self._translator.get("reports.filters.to_date", "To date")
                        )

            self.btnGenerate.setText(
                self._translator.get("reports.button.generate", "Generate Report")
            )
            self.btnExport.setText(
                self._translator.get("reports.button.export", "Export to CSV")
            )

            # Metric titles
            self._card_total_sales["title"].setText(
                self._translator.get("reports.metric.total_sales", "Total Sales")
            )
            self._card_total_profit["title"].setText(
                self._translator.get("reports.metric.total_profit", "Total Profit")
            )
            self._card_tx_count["title"].setText(
                self._translator.get("reports.metric.tx_count", "Transaction Count")
            )

            # Table headers
            headers = [
                self._translator.get("reports.table.column.id", "ID"),
                self._translator.get(
                    "reports.table.column.date", "Date"
                ),
                self._translator.get(
                    "reports.table.column.customer", "Customer"
                ),
                self._translator.get(
                    "reports.table.column.total", "Total"
                ),
                self._translator.get(
                    "reports.table.column.discount", "Discount"
                ),
            ]
            self.tblInvoices.setHorizontalHeaderLabels(headers)
        except Exception as exc:
            logger.error("Error applying translations in ReportsView: %s", exc, exc_info=True)

    # ------------------------------------------------------------------ #
    # Signals
    # ------------------------------------------------------------------ #
    def _connect_signals(self) -> None:
        self.btnGenerate.clicked.connect(self._generate_report)
        self.btnExport.clicked.connect(self._export_to_csv)

    # ------------------------------------------------------------------ #
    # Data loading
    # ------------------------------------------------------------------ #
    def _load_default_range(self) -> None:
        today = QDate.currentDate()
        start = today.addDays(-6)
        self.date_from.setDate(start)
        self.date_to.setDate(today)

    def _get_date_range(self) -> tuple[date, date]:
        q_from = self.date_from.date()
        q_to = self.date_to.date()
        d_from = date(q_from.year(), q_from.month(), q_from.day())
        d_to = date(q_to.year(), q_to.month(), q_to.day())
        if d_from > d_to:
            d_from, d_to = d_to, d_from
        return d_from, d_to

    def _generate_report(self) -> None:
        try:
            d_from, d_to = self._get_date_range()
            logger.info("Generating reports for range %s to %s", d_from, d_to)

            rows, total_sales, total_profit, tx_count, daily_totals = self._query_invoices(
                d_from,
                d_to,
            )

            # Update metrics
            self._card_total_sales["value"].setText(self._format_money(total_sales))
            self._card_total_profit["value"].setText(self._format_money(total_profit))
            self._card_tx_count["value"].setText(str(tx_count))

            # Update chart
            labels = [day.strftime("%Y-%m-%d") for day in sorted(daily_totals.keys())]
            values = [daily_totals[day] for day in sorted(daily_totals.keys())]

            chart_title = self._reshape_text(
                self._translator.get(
                    "reports.chart.daily_sales",
                    "Daily Sales",
                )
            )
            display_labels = [self._reshape_text(label) for label in labels]
            y_label = self._reshape_text(
                self._translator.get("reports.chart.y_axis", "Sales")
            )
            self.chart_widget.plot_daily_sales(
                display_labels,
                values,
                title=chart_title,
                y_label=y_label,
            )

            # Update table
            self._populate_table(rows)
        except Exception as exc:
            logger.error("Error generating report: %s", exc, exc_info=True)
            QMessageBox.critical(
                self,
                self._translator.get("dialog.error_title", "Error"),
                str(exc),
            )

    def _query_invoices(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[List[InvoiceRow], Decimal, Decimal, int, dict[date, Decimal]]:
        rows: List[InvoiceRow] = []
        total_sales = Decimal("0")
        total_profit = Decimal("0")
        tx_count = 0
        daily_totals: dict[date, Decimal] = {}

        with SessionLocal() as session:
            inv_alias = Invoice
            cust_alias = Customer

            query = (
                session.query(inv_alias, cust_alias)
                .outerjoin(cust_alias, inv_alias.CustID == cust_alias.CustID)
                .filter(
                    inv_alias.Date >= datetime.combine(
                        start_date, datetime.min.time()
                    ),
                    inv_alias.Date <= datetime.combine(
                        end_date, datetime.max.time()
                    ),
                    inv_alias.Status != "Void",
                )
                .order_by(inv_alias.Date.asc())
            )

            for inv, cust in query.all():
                inv_total = Decimal(str(inv.TotalAmount or 0))
                inv_discount = Decimal(str(inv.Discount or 0))
                total_sales += inv_total
                tx_count += 1

                inv_date = inv.Date or datetime.utcnow()
                day_key = inv_date.date()
                daily_totals[day_key] = daily_totals.get(day_key, Decimal("0")) + inv_total

                if cust is not None:
                    customer_name = cust.FullName or cust.Phone or ""
                else:
                    customer_name = ""

                rows.append(
                    InvoiceRow(
                        inv_id=inv.InvID,
                        inv_date=inv_date,
                        customer_name=customer_name,
                        total_amount=inv_total,
                        discount=inv_discount,
                    )
                )

            # Profit placeholder: if you later add batch-level cost data,
            # compute it here. For now profit is equal to total sales.
            total_profit = total_sales

        return rows, total_sales, total_profit, tx_count, daily_totals

    def _populate_table(self, rows: List[InvoiceRow]) -> None:
        self.tblInvoices.setRowCount(0)
        for idx, row in enumerate(rows):
            self.tblInvoices.insertRow(idx)

            id_item = QTableWidgetItem(str(row.inv_id))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

            date_item = QTableWidgetItem(row.inv_date.strftime("%Y-%m-%d %H:%M"))
            customer_item = QTableWidgetItem(row.customer_name)

            total_item = QTableWidgetItem(self._format_money(row.total_amount))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            discount_item = QTableWidgetItem(self._format_money(row.discount))
            discount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.tblInvoices.setItem(idx, 0, id_item)
            self.tblInvoices.setItem(idx, 1, date_item)
            self.tblInvoices.setItem(idx, 2, customer_item)
            self.tblInvoices.setItem(idx, 3, total_item)
            self.tblInvoices.setItem(idx, 4, discount_item)

    def _export_to_csv(self) -> None:
        try:
            if self.tblInvoices.rowCount() == 0:
                QMessageBox.information(
                    self,
                    self._translator.get("dialog.info_title", "Information"),
                    self._translator.get(
                        "reports.export.no_data", "There is no data to export."
                    ),
                )
                return

            filename, _ = QFileDialog.getSaveFileName(
                self,
                self._translator.get(
                    "reports.export.save_dialog_title", "Save report as CSV"
                ),
                "report.csv",
                "CSV Files (*.csv)",
            )
            if not filename:
                return

            with open(filename, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                headers = [
                    self.tblInvoices.horizontalHeaderItem(col).text()
                    for col in range(self.tblInvoices.columnCount())
                ]
                writer.writerow(headers)

                for row in range(self.tblInvoices.rowCount()):
                    row_data: List[str] = []
                    for col in range(self.tblInvoices.columnCount()):
                        item = self.tblInvoices.item(row, col)
                        row_data.append(item.text() if item is not None else "")
                    writer.writerow(row_data)

            QMessageBox.information(
                self,
                self._translator.get("dialog.info_title", "Information"),
                self._translator.get(
                    "reports.export.success",
                    "Report exported successfully.",
                ),
            )
        except Exception as exc:
            logger.error("Error exporting report to CSV: %s", exc, exc_info=True)
            QMessageBox.critical(
                self,
                self._translator.get("dialog.error_title", "Error"),
                str(exc),
            )

    @staticmethod
    def _format_money(amount: Decimal) -> str:
        try:
            return f"{float(amount):,.2f}"
        except Exception:
            return str(amount)