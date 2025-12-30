from __future__ import annotations

from typing import Optional

from PyQt6 import uic
from PyQt6.QtWidgets import QAbstractItemView, QWidget


class InventoryView(QWidget):
    """
    Inventory module scaffold.

    Loads its layout from app/views/ui/inventory_view.ui and configures the
    products table. Detailed behaviors will be implemented in later phases.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        uic.loadUi("app/views/ui/inventory_view.ui", self)

        self._setup_products_table()

    def _setup_products_table(self) -> None:
        headers = ["ID", "Name", "Barcode", "Stock", "Price"]
        self.tblProducts.setColumnCount(len(headers))
        self.tblProducts.setHorizontalHeaderLabels(headers)

        self.tblProducts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tblProducts.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tblProducts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        if self.tblProducts.verticalHeader() is not None:
            self.tblProducts.verticalHeader().setVisible(False)

        if self.tblProducts.horizontalHeader() is not None:
            self.tblProducts.horizontalHeader().setStretchLastSection(True)