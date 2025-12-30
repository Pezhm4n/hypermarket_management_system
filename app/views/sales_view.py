from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.sales_controller import SalesController
from app.core.translation_manager import TranslationManager
from app.models.models import UserAccount

logger = logging.getLogger(__name__)


class SalesView(QWidget):
    """
    Point-of-Sale (POS) view for the Sales module.

    Loads its layout from app/views/ui/sales_view.ui and wires the UI
    elements to SalesController, handling barcode scanning, cart management,
    and checkout.
    """

    def __init__(
        self,
        translation_manager: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._translator = translation_manager
        self._controller = SalesController()
        self._current_user: Optional[UserAccount] = None
        self._active_shift_id: Optional[int] = None

        uic.loadUi("app/views/ui/sales_view.ui", self)

        self._inject_close_shift_button()
        self._setup_cart_table()
        self._setup_shortcuts()
        self._connect_signals()
        self._reset_total()

        self._translator.language_changed.connect(self._on_language_changed)
        self._apply_translations()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def set_current_user(self, user: UserAccount) -> None:
        try:
            logger.info(
                "SalesView current user set: UserID=%s, Username=%s",
                getattr(user, "UserID", None),
                getattr(user, "Username", None),
            )
            self._current_user = user
            self.ensure_active_shift()
        except Exception as e:
            logger.error("Error in set_current_user: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    # ------------------------------------------------------------------ #
    # UI setup
    # ------------------------------------------------------------------ #
    def _inject_close_shift_button(self) -> None:
        try:
            layout = getattr(self, "horizontalLayout_bottom", None)
            if layout is None:
                logger.warning(
                    "SalesView bottom layout not found; cannot inject Close Shift button."
                )
                return

            self.btnCloseShift = QPushButton(self)
            self.btnCloseShift.setObjectName("btnCloseShift")
            self.btnCloseShift.setText("Close Shift")

            insert_index = max(0, layout.count() - 1)
            layout.insertWidget(insert_index, self.btnCloseShift)
            self.btnCloseShift.clicked.connect(self._on_close_shift_clicked)

            logger.info("Close Shift button injected into SalesView layout.")
        except Exception as e:
            logger.error("Error in _inject_close_shift_button: %s", e, exc_info=True)

    def _on_language_changed(self, language: str) -> None:
        try:
            logger.info("SalesView language changed to: %s", language)
            _ = language
            self._apply_translations()
        except Exception as e:
            logger.error("Error in _on_language_changed: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _apply_translations(self) -> None:
        """
        Apply localized texts to labels, buttons and headers.
        """
        try:
            self.setWindowTitle(self._translator["sales.page_title"])
            self.txtBarcode.setPlaceholderText(
                self._translator["sales.barcode_placeholder"]
            )
            self.btnSearch.setText(self._translator["sales.search_button"])
            self.btnCheckout.setText(self._translator["sales.checkout_button"])

            if hasattr(self, "btnCloseShift"):
                self.btnCloseShift.setText("Close Shift")

            self._setup_cart_table()
            self._reset_total()
        except Exception as e:
            logger.error("Error in _apply_translations: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _setup_cart_table(self) -> None:
        headers = [
            self._translator["sales.table.column.name"],
            self._translator["sales.table.column.quantity"],
            self._translator["sales.table.column.price"],
            self._translator["sales.table.column.row_total"],
        ]
        self.tblCart.setColumnCount(len(headers))
        self.tblCart.setHorizontalHeaderLabels(headers)

        self.tblCart.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tblCart.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tblCart.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        if self.tblCart.verticalHeader() is not None:
            self.tblCart.verticalHeader().setVisible(False)

        if self.tblCart.horizontalHeader() is not None:
            self.tblCart.horizontalHeader().setStretchLastSection(True)

    def _setup_shortcuts(self) -> None:
        # Allow deleting the selected cart row with the Delete key
        self._delete_shortcut = QShortcut(QKeySequence("Delete"), self.tblCart)
        self._delete_shortcut.activated.connect(self._remove_selected_row)

    def _connect_signals(self) -> None:
        self.txtBarcode.returnPressed.connect(self._on_barcode_entered)
        self.btnSearch.clicked.connect(self._on_barcode_entered)
        self.btnCheckout.clicked.connect(self._on_checkout_clicked)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _format_money(self, amount: Decimal) -> str:
        quantized = amount.quantize(Decimal("0.01"))
        return f"{float(quantized):.2f}"

    def _reset_total(self) -> None:
        total_text = self._translator["sales.total_prefix"].format(
            amount=self._format_money(Decimal("0"))
        )
        self.lblTotalAmount.setText(total_text)

    def _find_cart_row_by_prod_id(self, prod_id: int) -> int:
        for row in range(self.tblCart.rowCount()):
            item = self.tblCart.item(row, 0)
            if item is None:
                continue
            value = item.data(Qt.ItemDataRole.UserRole)
            if value == prod_id:
                return row
        return -1

    def _add_or_increment_cart_item(self, product: Dict[str, Any]) -> None:
        prod_id = int(product["ProdID"])
        name = str(product["Name"])
        unit_price = Decimal(str(product.get("BasePrice", 0)))

        existing_row = self._find_cart_row_by_prod_id(prod_id)

        if existing_row != -1:
            qty_item = self.tblCart.item(existing_row, 1)
            if qty_item is None:
                return

            try:
                current_qty = Decimal(qty_item.text())
            except Exception:
                current_qty = Decimal("0")

            new_qty = current_qty + Decimal("1")
            qty_item.setText(str(int(new_qty)))

            row_total_item = self.tblCart.item(existing_row, 3)
            if row_total_item is not None:
                row_total = new_qty * unit_price
                row_total_item.setText(self._format_money(row_total))

            return

        row = self.tblCart.rowCount()
        self.tblCart.insertRow(row)

        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.ItemDataRole.UserRole, prod_id)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        qty_item = QTableWidgetItem("1")
        qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        qty_item.setFlags(qty_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        price_item = QTableWidgetItem(self._format_money(unit_price))
        price_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        price_item.setFlags(price_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        row_total_item = QTableWidgetItem(self._format_money(unit_price))
        row_total_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row_total_item.setFlags(
            row_total_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )

        self.tblCart.setItem(row, 0, name_item)
        self.tblCart.setItem(row, 1, qty_item)
        self.tblCart.setItem(row, 2, price_item)
        self.tblCart.setItem(row, 3, row_total_item)

    def _remove_selected_row(self) -> None:
        try:
            logger.info("Delete shortcut activated in SalesView.")
            row = self.tblCart.currentRow()
            if row < 0:
                return

            self.tblCart.removeRow(row)
            self._recalculate_total()
        except Exception as e:
            logger.error("Error in _remove_selected_row: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _collect_cart_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        for row in range(self.tblCart.rowCount()):
            name_item = self.tblCart.item(row, 0)
            qty_item = self.tblCart.item(row, 1)
            price_item = self.tblCart.item(row, 2)

            if name_item is None or qty_item is None or price_item is None:
                continue

            prod_id = name_item.data(Qt.ItemDataRole.UserRole)
            if prod_id is None:
                continue

            try:
                quantity = Decimal(qty_item.text())
            except Exception:
                quantity = Decimal("0")

            try:
                unit_price = Decimal(price_item.text())
            except Exception:
                unit_price = Decimal("0")

            items.append(
                {
                    "ProdID": int(prod_id),
                    "Quantity": quantity,
                    "UnitPrice": unit_price,
                }
            )

        return items

    def _recalculate_total(self) -> None:
        cart_items = self._collect_cart_items()
        if not cart_items:
            self._reset_total()
            return

        total = self._controller.calculate_cart_total(cart_items)
        total_text = self._translator["sales.total_prefix"].format(
            amount=self._format_money(total)
        )
        self.lblTotalAmount.setText(total_text)

    def _prompt_start_shift(self) -> Optional[Decimal]:
        try:
            while True:
                dialog = QDialog(self)
                dialog.setWindowTitle("Start Shift")

                layout = QVBoxLayout(dialog)

                label_title = QLabel("Start a new shift?", dialog)
                layout.addWidget(label_title)

                label_cash = QLabel("Cash Float (Mojoodee Avaliyeh):", dialog)
                layout.addWidget(label_cash)

                txt_cash = QLineEdit(dialog)
                txt_cash.setText("0")
                layout.addWidget(txt_cash)

                button_box = QDialogButtonBox(
                    QDialogButtonBox.StandardButton.Ok
                    | QDialogButtonBox.StandardButton.Cancel,
                    parent=dialog,
                )
                layout.addWidget(button_box)

                button_box.accepted.connect(dialog.accept)
                button_box.rejected.connect(dialog.reject)

                result = dialog.exec()
                if result != QDialog.DialogCode.Accepted:
                    logger.info("User cancelled start shift dialog.")
                    return None

                raw = txt_cash.text().strip()
                try:
                    amount = Decimal(raw or "0")
                except Exception:
                    QMessageBox.warning(
                        self,
                        "Invalid amount",
                        "Please enter a valid cash float amount.",
                    )
                    continue

                if amount < 0:
                    QMessageBox.warning(
                        self,
                        "Invalid amount",
                        "Cash float cannot be negative.",
                    )
                    continue

                amount = amount.quantize(Decimal("0.01"))
                logger.info("User entered cash float amount: %s", amount)
                return amount
        except Exception as e:
            logger.error("Error in _prompt_start_shift: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))
            return None

    def ensure_active_shift(self) -> None:
        """
        Ensure that there is an active shift for the current user.

        If none exists, the user is prompted to start a new shift with a cash float.
        """
        try:
            if self._current_user is None:
                logger.warning(
                    "ensure_active_shift called with no current user; aborting."
                )
                return

            emp_id = getattr(self._current_user, "EmpID", None)
            if emp_id is None:
                logger.warning(
                    "ensure_active_shift could not determine EmpID for current user."
                )
                QMessageBox.critical(
                    self,
                    "Error",
                    "Current employee could not be determined.",
                )
                return

            existing_shift_id = self._controller.get_active_shift(emp_id)
            if existing_shift_id is not None:
                logger.info(
                    "Reusing existing active shift ShiftID=%s for EmpID=%s.",
                    existing_shift_id,
                    emp_id,
                )
                self._active_shift_id = existing_shift_id
                return

            cash_float = self._prompt_start_shift()
            if cash_float is None:
                logger.info(
                    "No cash float provided; active shift will not be created."
                )
                return

            shift_id = self._controller.start_shift(emp_id, cash_float)
            self._active_shift_id = shift_id
            QMessageBox.information(
                self,
                "Shift Started",
                f"Shift started successfully.\nShift ID: {shift_id}",
            )
        except Exception as e:
            logger.error("Error in ensure_active_shift: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _resolve_shift_id(self) -> int:
        """
        Determine which ShiftID to use for checkout.

        Uses the current logged-in user (set by MainView) and the controller
        for an active shift. If no shift exists, prompts the user to open one.
        """
        try:
            if self._active_shift_id is None:
                self.ensure_active_shift()

            if self._active_shift_id is None:
                raise ValueError("No active shift is open for the current user.")

            logger.info("Resolved active ShiftID=%s for checkout.", self._active_shift_id)
            return self._active_shift_id
        except Exception as e:
            logger.error("Error in _resolve_shift_id: %s", e, exc_info=True)
            raise

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_barcode_entered(self) -> None:
        try:
            raw_barcode = self.txtBarcode.text()
            barcode = raw_barcode.strip() if raw_barcode is not None else ""
            logger.info("Barcode entered: %s", barcode)

            if not barcode:
                return

            product = self._controller.get_product_details(barcode)
            self.txtBarcode.clear()

            if product is None:
                logger.warning("No product found for barcode '%s'.", barcode)
                QMessageBox.warning(self, "خطا", "کالا یافت نشد")
                return

            total_stock = product.get("TotalStock")
            try:
                total_stock_dec = Decimal(str(total_stock))
            except Exception:
                total_stock_dec = Decimal("0")

            if total_stock_dec <= 0:
                logger.warning(
                    "Product out of stock: ProdID=%s, Name='%s', Barcode='%s'",
                    product.get("ProdID"),
                    product.get("Name"),
                    barcode,
                )
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator["sales.error.out_of_stock"].format(
                        name=product.get("Name")
                    ),
                )
                return

            self._add_or_increment_cart_item(product)
            self._recalculate_total()
        except Exception as e:
            logger.error("Error in _on_barcode_entered: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))
            self.txtBarcode.clear()

    def _on_checkout_clicked(self) -> None:
        try:
            logger.info("Checkout button clicked.")

            if self.tblCart.rowCount() == 0:
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator["sales.info.cart_empty"],
                )
                return

            cart_items = self._collect_cart_items()
            if not cart_items:
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator["sales.info.cart_empty"],
                )
                return

            total = self._controller.calculate_cart_total(cart_items)
            logger.info("Calculated checkout total: %s", total)

            shift_id = self._resolve_shift_id()

            success = self._controller.process_checkout(
                shift_id=shift_id,
                cart_items=cart_items,
                total_amount=total,
                payment_method="Cash",
            )

            if success:
                logger.info(
                    "Checkout completed successfully. ShiftID=%s, Total=%s",
                    shift_id,
                    total,
                )
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator["sales.info.success"],
                )
                self._clear_cart()
        except Exception as e:
            logger.error("Error in _on_checkout_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _on_close_shift_clicked(self) -> None:
        try:
            logger.info("Close Shift button clicked.")

            if self._active_shift_id is None:
                QMessageBox.warning(
                    self,
                    "No Active Shift",
                    "There is no active shift to close.",
                )
                return

            confirm = QMessageBox.question(
                self,
                "Close Shift",
                "Are you sure you want to close the current shift?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                logger.info("User cancelled closing shift.")
                return

            summary = self._controller.close_shift(self._active_shift_id)
            total_sales = summary.get("total_sales", Decimal("0"))
            invoice_count = summary.get("invoice_count", 0)

            formatted_total = f"{float(total_sales):,.2f}"

            QMessageBox.information(
                self,
                "Shift Closed",
                f"Shift closed successfully.\n\n"
                f"Total sales in this shift: {formatted_total}\n"
                f"Total invoices: {invoice_count}",
            )

            self._active_shift_id = None
        except Exception as e:
            logger.error("Error in _on_close_shift_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _clear_cart(self) -> None:
        self.tblCart.setRowCount(0)
        self._reset_total()
        self.txtBarcode.clear()
        self.txtBarcode.setFocus()