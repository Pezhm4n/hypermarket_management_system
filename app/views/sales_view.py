from __future__ import annotations

from typing import Optional

from PyQt6 import uic
from PyQt6.QtWidgets import QAbstractItemView, QWidget


class SalesView(QWidget):
    """
    Point-of-Sale (POS) view for the Sales module.

    Loads its layout from app/views/ui/sales_view.ui and configures the
    cart table for displaying line items.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        uic.loadUi("app/views/ui/sales_view.ui", self)

        self._setup_cart_table()

    def _setup_cart_table(self) -> None:
        headers = ["Item Name", "Quantity", "Price", "Row Total"]
        self.tblCart.setColumnCount(len(headers))
        self.tblCart.setHorizontalHeaderLabels(headers)

        self.tblCart.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tblCart.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tblCart.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        if self.tblCart.verticalHeader() is not None:
            self.tblCart.verticalHeader().setVisible(False)

        if self.tblCart.horizontalHeader() is not None:
            self.tblCart.horizontalHeader().setStretchLastSection(True)