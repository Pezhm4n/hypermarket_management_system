from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QMessageBox,
    QShortcut,
    QTableWidgetItem,
    QWidget,
)

from app.controllers.sales_controller import SalesController


class SalesView(QWidget):
    """
    Point-of-Sale (POS) view for the Sales module.

    Loads its layout from app/views/ui/sales_view.ui and wires the UI
    elements to SalesController, handling barcode scanning, cart management,
    and checkout.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        uic.loadUi("app/views/ui/sales_view.ui", self)

        self._controller = SalesController()

        self._setup_cart_table()
        self._setup_shortcuts()
        self._connect_signals()
        self._reset_total()

    # ------------------------------------------------------------------ #
    # UI setup
    # ------------------------------------------------------------------ #
    def _setup_cart_table(self) -> None:
        headers = ["Item Name", "Quantity", "Price", "Row Total"]
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
        self.btnCheckout.clicked.connect(self._on_checkout_clicked)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _format_money(self, amount: Decimal) -> str:
        quantized = amount.quantize(Decimal("0.01"))
        return f"{float(quantized):.2f}"

    def _reset_total(self) -> None:
        self.lblTotalAmount.setText("Total: 0.00")

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
        row = self.tblCart.currentRow()
        if row < 0:
            return

        self.tblCart.removeRow(row)
        self._recalculate_total()

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
        self.lblTotalAmount.setText(f"Total: {self._format_money(total)}")

    def _resolve_shift_id(self) -> int:
        """
        Determine which ShiftID to use for checkout.

        For Phase 4, we pragmatically derive the employee from the parent
        MainView (current_user) and ask the controller for an active shift.
        """
        parent = self.parent()
        user = getattr(parent, "current_user", None) if parent is not None else None
        emp_id = getattr(user, "EmpID", None) if user is not None else None
        return self._controller.get_or_create_active_shift(emp_id)

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_barcode_entered(self) -> None:
        barcode = self.txtBarcode.text().strip()
        if not barcode:
            return

        try:
            product = self._controller.get_product_details(barcode)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Lookup error",
                f"Failed to lookup product:\n{exc}",
            )
            self.txtBarcode.clear()
            return

        self.txtBarcode.clear()

        if product is None:
            QMessageBox.warning(
                self,
                "Not found",
                f"No product found for barcode '{barcode}'.",
            )
            return

        total_stock = product.get("TotalStock")
        try:
            total_stock_dec = Decimal(str(total_stock))
        except Exception:
            total_stock_dec = Decimal("0")

        if total_stock_dec <= 0:
            QMessageBox.warning(
                self,
                "Out of stock",
                f"Product '{product.get('Name')}' is out of stock.",
            )
            return

        self._add_or_increment_cart_item(product)
        self._recalculate_total()

    def _on_checkout_clicked(self) -> None:
        if self.tblCart.rowCount() == 0:
            QMessageBox.information(
                self,
                "Cart is empty",
                "There are no items in the cart.",
            )
            return

        cart_items = self._collect_cart_items()
        if not cart_items:
            QMessageBox.information(
                self,
                "Cart is empty",
                "There are no items in the cart.",
            )
            return

        total = self._controller.calculate_cart_total(cart_items)

        try:
            shift_id = self._resolve_shift_id()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Shift error",
                f"Unable to determine active shift:\n{exc}",
            )
            return

        try:
            success = self._controller.process_checkout(
                shift_id=shift_id,
                cart_items=cart_items,
                total_amount=total,
                payment_method="Cash",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Checkout failed",
                f"Could not complete checkout:\n{exc}",
            )
            return

        if success:
            QMessageBox.information(
                self,
                "Success",
                "Invoice saved successfully.",
            )
            self._clear_cart()

    def _clear_cart(self) -> None:
        self.tblCart.setRowCount(0)
        self._reset_total()
        self.txtBarcode.clear()
        self.txtBarcode.setFocus()