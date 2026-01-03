from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.sales_controller import SalesController
from app.core.translation_manager import TranslationManager
from app.models.models import Invoice, InvoiceItem

logger = logging.getLogger(__name__)


class ReturnDialog(QDialog):
    """
    Dialog for processing returns/refunds against an existing invoice.

    The dialog lets the user:
        * Enter an invoice ID and load its details.
        * See original quantities and previously returned quantities.
        * Enter per-line quantities to return and free-text reasons.
        * Confirm the return, which updates inventory and loyalty via
          SalesController.process_return().
    """

    def __init__(
        self,
        translation_manager: TranslationManager,
        controller: Optional[SalesController] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translation_manager
        self._controller = controller or SalesController()

        self._invoice: Optional[Invoice] = None
        self._refund_amount: Decimal = Decimal("0")

        try:
            self._build_ui()
            self._apply_translations()
        except Exception as exc:
            logger.error("Error initializing ReturnDialog UI: %s", exc, exc_info=True)

    # ------------------------------------------------------------------ #
    # UI helpers
    # ------------------------------------------------------------------ #
    def _tr(self, key: str, default: str) -> str:
        try:
            return self._translator.get(key, default)
        except Exception:
            return default

    def _build_ui(self) -> None:
        self.setModal(True)
        self.setMinimumSize(720, 520)

        # تنظیم جهت صفحه (RTL/LTR)
        if self._translator and getattr(self._translator, "language", "en") == "fa":
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self.setWindowTitle(self._tr("return.dialog.title", "Returns / Refund"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Invoice selection row
        select_row = QHBoxLayout()
        select_row.setSpacing(8)
        self.lblInvoicePrompt = QLabel(self)
        self.txtInvoiceId = QLineEdit(self)
        self.txtInvoiceId.setObjectName("txtInvoiceId")
        self.txtInvoiceId.setValidator(QIntValidator(1, 10_000_000, self))
        self.btnLoadInvoice = QPushButton(self)
        self.btnLoadInvoice.setObjectName("btnLoadInvoice")
        select_row.addWidget(self.lblInvoicePrompt)
        select_row.addWidget(self.txtInvoiceId)
        select_row.addWidget(self.btnLoadInvoice)
        layout.addLayout(select_row)

        # Invoice summary
        self.lblInvoiceSummary = QLabel(self)
        self.lblInvoiceSummary.setObjectName("lblInvoiceSummary")
        self.lblInvoiceSummary.setWordWrap(True)
        layout.addWidget(self.lblInvoiceSummary)

        # Items table
        self.tblItems = QTableWidget(self)
        self.tblItems.setObjectName("tblReturnItems")
        self.tblItems.setColumnCount(5)
        self.tblItems.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tblItems.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tblItems.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        header = self.tblItems.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tblItems)

        # Refund summary
        summary_row = QHBoxLayout()
        summary_row.addStretch(1)
        self.lblRefundTotal = QLabel(self)
        self.lblRefundTotal.setObjectName("lblRefundTotal")
        summary_row.addWidget(self.lblRefundTotal)
        layout.addLayout(summary_row)

        # Dialog buttons
        # --- تغییر مهم: استفاده از self.button_box ---
        # این تغییر باعث می‌شود بتوانیم در تابع ترجمه به دکمه‌ها دسترسی داشته باشیم
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        layout.addWidget(self.button_box)

        # Wire signals
        self.btnLoadInvoice.clicked.connect(self._on_load_invoice_clicked)
        # اتصال سیگنال‌ها با استفاده از self.button_box
        self.button_box.accepted.connect(self._on_confirm_clicked)
        self.button_box.rejected.connect(self.reject)

    def _apply_translations(self) -> None:
        try:
            self.setWindowTitle(self._tr("return.dialog.title", "Returns / Refund"))
            self.lblInvoicePrompt.setText(
                self._tr("return.invoice_id_label", "Invoice ID:")
            )
            self.btnLoadInvoice.setText(self._tr("return.load_button", "Load"))

            headers = [
                self._tr("return.table.header.product", "Product"),
                self._tr("return.table.header.original_qty", "Original Qty"),
                self._tr("return.table.header.returned_qty", "Previously Returned"),
                self._tr("return.table.header.return_now", "Return Now"),
                self._tr("return.table.header.reason", "Reason"),
            ]
            self.tblItems.setHorizontalHeaderLabels(headers)
            
            # --- ترجمه دکمه‌های استاندارد ---
            # بررسی می‌کنیم که button_box وجود داشته باشد
            if hasattr(self, "button_box"):
                # دریافت دکمه OK و تغییر متن آن
                btn_ok = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
                if btn_ok:
                    btn_ok.setText(self._tr("dialog.button.ok", "OK"))
                
                # دریافت دکمه Cancel و تغییر متن آن
                btn_cancel = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
                if btn_cancel:
                    btn_cancel.setText(self._tr("dialog.button.cancel", "Cancel"))
            # -----------------------------

            self._update_invoice_summary()
            self._update_refund_label()
        except Exception as exc:
            logger.error("Error in ReturnDialog._apply_translations: %s", exc, exc_info=True)

    def _format_money(self, value: Any) -> str:
        try:
            dec = (
                value
                if isinstance(value, Decimal)
                else Decimal(str(value or "0"))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            dec = Decimal("0.00")
        return f"{float(dec):,.2f}"

    def _update_invoice_summary(self) -> None:
        if self._invoice is None:
            self.lblInvoiceSummary.setText(
                self._tr("return.invoice_summary.empty", "No invoice loaded.")
            )
            return

        inv = self._invoice
        try:
            date_value = getattr(inv, "Date", None)
            if hasattr(date_value, "strftime"):
                date_str = date_value.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = str(date_value) if date_value is not None else "-"
        except Exception:
            date_str = "-"

        customer_name = "-"
        try:
            if getattr(inv, "customer", None) is not None:
                customer_name = (
                    inv.customer.FullName
                    or inv.customer.Phone
                    or "-"
                )
        except Exception:
            customer_name = "-"

        try:
            total_amount = self._format_money(inv.TotalAmount or 0)
        except Exception:
            total_amount = self._format_money(Decimal("0"))

        template = self._tr(
            "return.invoice_summary.template",
            "Invoice #{id} | Date: {date} | Customer: {customer} | Total: {total}",
        )
        self.lblInvoiceSummary.setText(
            template.format(
                id=getattr(inv, "InvID", "?"),
                date=date_str,
                customer=customer_name,
                total=total_amount,
            )
        )

    def _update_refund_label(self) -> None:
        template = self._tr(
            "return.total_refund_label",
            "Total Refund: {amount}",
        )
        self.lblRefundTotal.setText(
            template.format(amount=self._format_money(self._refund_amount))
        )

    # ------------------------------------------------------------------ #
    # Data loading and table preparation
    # ------------------------------------------------------------------ #
    def _on_load_invoice_clicked(self) -> None:
        try:
            text = (self.txtInvoiceId.text() or "").strip()
            if not text:
                QMessageBox.warning(
                    self,
                    self._tr("dialog.warning_title", "Warning"),
                    self._tr("return.error.no_invoice_id", "Please enter an invoice ID."),
                )
                return

            try:
                invoice_id = int(text)
            except Exception:
                QMessageBox.warning(
                    self,
                    self._tr("dialog.warning_title", "Warning"),
                    self._tr(
                        "return.error.invalid_invoice_id",
                        "Invoice ID must be a valid number.",
                    ),
                )
                return

            logger.info("Loading invoice %s for return.", invoice_id)
            invoice = self._controller.find_invoice(invoice_id)
            self._invoice = invoice
            self._populate_items_table(invoice)
            self._refund_amount = Decimal("0")
            self._update_invoice_summary()
            self._update_refund_label()
        except ValueError as exc:
            logger.warning("Invoice load validation error: %s", exc, exc_info=True)
            QMessageBox.warning(
                self,
                self._tr("dialog.warning_title", "Warning"),
                str(exc),
            )
        except Exception as exc:
            logger.error("Unexpected error loading invoice for return: %s", exc, exc_info=True)
            QMessageBox.critical(
                self,
                self._tr("dialog.error_title", "Error"),
                str(exc),
            )

    def _populate_items_table(self, invoice: Invoice) -> None:
        try:
            self.tblItems.setRowCount(0)
            items: Iterable[InvoiceItem] = invoice.items or []

            for item in items:
                try:
                    original_qty = Decimal(str(item.Quantity or 0))
                except Exception:
                    original_qty = Decimal("0")

                already_returned = sum(
                    Decimal(str(ri.Quantity or 0))
                    for ri in (item.return_items or [])
                )
                remaining_qty = original_qty - already_returned

                if original_qty <= 0 or remaining_qty <= 0:
                    # Nothing left to return for this line
                    continue

                # Compute per-unit refund based on recorded line total
                try:
                    line_total = Decimal(str(item.LineTotal or 0))
                except Exception:
                    line_total = Decimal("0")

                if original_qty <= 0:
                    unit_refund = Decimal("0")
                else:
                    unit_refund = (line_total / original_qty).quantize(
                        Decimal("0.0001"),
                        rounding=ROUND_HALF_UP,
                    )

                row = self.tblItems.rowCount()
                self.tblItems.insertRow(row)

                # Product name column (stores item_id and unit_refund in data)
                name = None
                try:
                    if getattr(item, "product", None) is not None:
                        name = item.product.Name
                except Exception:
                    name = None
                if not name:
                    name = f"#{item.ProdID}"

                name_item = QTableWidgetItem(name)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                name_item.setData(Qt.ItemDataRole.UserRole, int(item.ItemID))
                name_item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    str(unit_refund),
                )
                self.tblItems.setItem(row, 0, name_item)

                # Original quantity
                orig_item = QTableWidgetItem(self._format_money(original_qty))
                orig_item.setFlags(orig_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                orig_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.tblItems.setItem(row, 1, orig_item)

                # Previously returned
                prev_item = QTableWidgetItem(self._format_money(already_returned))
                prev_item.setFlags(prev_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                prev_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.tblItems.setItem(row, 2, prev_item)

                # Return now spinbox
                spin = QDoubleSpinBox(self.tblItems)
                spin.setDecimals(3)
                spin.setMinimum(0.0)
                spin.setMaximum(float(remaining_qty))
                spin.setSingleStep(1.0)
                spin.setValue(0.0)
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spin.valueChanged.connect(self._recalculate_refund_total)
                self.tblItems.setCellWidget(row, 3, spin)

                # Reason field
                reason_edit = QLineEdit(self.tblItems)
                reason_edit.setPlaceholderText(
                    self._tr("return.reason_placeholder", "Reason (optional)")
                )
                self.tblItems.setCellWidget(row, 4, reason_edit)

            if self.tblItems.rowCount() == 0:
                QMessageBox.information(
                    self,
                    self._tr("dialog.info_title", "Information"),
                    self._tr(
                        "return.info.no_items_available",
                        "This invoice has no items available for return.",
                    ),
                )
        except Exception as exc:
            logger.error("Error populating return items table: %s", exc, exc_info=True)
            QMessageBox.critical(
                self,
                self._tr("dialog.error_title", "Error"),
                str(exc),
            )

    # ------------------------------------------------------------------ #
    # Refund calculation and payload preparation
    # ------------------------------------------------------------------ #
    def _recalculate_refund_total(self) -> None:
        try:
            total = Decimal("0")
            for row in range(self.tblItems.rowCount()):
                name_item = self.tblItems.item(row, 0)
                if name_item is None:
                    continue

                unit_refund_raw = name_item.data(Qt.ItemDataRole.UserRole + 1)
                try:
                    unit_refund = Decimal(str(unit_refund_raw or "0"))
                except Exception:
                    unit_refund = Decimal("0")

                spin_widget = self.tblItems.cellWidget(row, 3)
                spin: Optional[QDoubleSpinBox] = None
                if isinstance(spin_widget, QDoubleSpinBox):
                    spin = spin_widget
                elif isinstance(spin_widget, QWidget):
                    spin = spin_widget.findChild(QDoubleSpinBox)

                if spin is None:
                    continue

                try:
                    qty_dec = Decimal(str(spin.value()))
                except Exception:
                    qty_dec = Decimal("0")

                if qty_dec <= 0:
                    continue

                line_refund = (unit_refund * qty_dec).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
                total += line_refund

            self._refund_amount = total.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            self._update_refund_label()
        except Exception as exc:
            logger.error("Error recalculating refund total: %s", exc, exc_info=True)

    def _collect_return_items(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for row in range(self.tblItems.rowCount()):
            name_item = self.tblItems.item(row, 0)
            if name_item is None:
                continue

            item_id_raw = name_item.data(Qt.ItemDataRole.UserRole)
            if item_id_raw is None:
                continue

            spin_widget = self.tblItems.cellWidget(row, 3)
            spin: Optional[QDoubleSpinBox] = None
            if isinstance(spin_widget, QDoubleSpinBox):
                spin = spin_widget
            elif isinstance(spin_widget, QWidget):
                spin = spin_widget.findChild(QDoubleSpinBox)

            if spin is None:
                continue

            try:
                qty_dec = Decimal(str(spin.value()))
            except Exception:
                qty_dec = Decimal("0")

            if qty_dec <= 0:
                continue

            reason_widget = self.tblItems.cellWidget(row, 4)
            reason_text = ""
            if isinstance(reason_widget, QLineEdit):
                reason_text = (reason_widget.text() or "").strip()

            try:
                item_id_int = int(item_id_raw)
            except Exception:
                continue

            results.append(
                {
                    "item_id": item_id_int,
                    "quantity": qty_dec,
                    "reason": reason_text,
                }
            )

        return results

    # ------------------------------------------------------------------ #
    # Confirm and apply return
    # ------------------------------------------------------------------ #
    def _on_confirm_clicked(self) -> None:
        try:
            if self._invoice is None:
                QMessageBox.warning(
                    self,
                    self._tr("dialog.warning_title", "Warning"),
                    self._tr(
                        "return.error.no_invoice_loaded",
                        "Please load an invoice before confirming a return.",
                    ),
                )
                return

            payload = self._collect_return_items()
            if not payload:
                QMessageBox.information(
                    self,
                    self._tr("dialog.info_title", "Information"),
                    self._tr(
                        "return.info.no_quantities_entered",
                        "Please enter at least one quantity to return.",
                    ),
                )
                return

            if self._refund_amount <= 0:
                self._recalculate_refund_total()

            if self._refund_amount <= 0:
                QMessageBox.information(
                    self,
                    self._tr("dialog.info_title", "Information"),
                    self._tr(
                        "return.info.zero_refund",
                        "The total refund amount is zero.",
                    ),
                )
                return

            confirm_text = self._tr(
                "return.confirm_message",
                "Process return with total refund {amount}?",
            ).format(amount=self._format_money(self._refund_amount))

            confirm = QMessageBox.question(
                self,
                self._tr("dialog.confirm_title", "Confirm"),
                confirm_text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

            refund_amount = self._controller.process_return(
                invoice_id=self._invoice.InvID,
                return_items=payload,
            )
            self._refund_amount = refund_amount
            self._update_refund_label()

            success_msg = self._tr(
                "return.success_message",
                "Return processed successfully. Refund amount: {amount}",
            ).format(amount=self._format_money(refund_amount))

            QMessageBox.information(
                self,
                self._tr("dialog.info_title", "Information"),
                success_msg,
            )
            self.accept()
        except ValueError as exc:
            logger.warning("Validation error while processing return: %s", exc, exc_info=True)
            QMessageBox.warning(
                self,
                self._tr("dialog.warning_title", "Warning"),
                str(exc),
            )
        except Exception as exc:
            logger.error("Unexpected error while processing return: %s", exc, exc_info=True)
            QMessageBox.critical(
                self,
                self._tr("dialog.error_title", "Error"),
                str(exc),
            )