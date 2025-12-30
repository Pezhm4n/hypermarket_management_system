from __future__ import annotations

from typing import Optional

from PyQt6 import uic
from PyQt6.QtWidgets import QAbstractItemView, QWidget

from app.core.translation_manager import TranslationManager


class InventoryView(QWidget):
    """
    Inventory module scaffold.

    Loads its layout from app/views/ui/inventory_view.ui and configures the
    products table. Detailed behaviors will be implemented in later phases.
    """

    def __init__(
        self,
        translation_manager: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translation_manager

        uic.loadUi("app/views/ui/inventory_view.ui", self)

        self._translator.language_changed.connect(self._on_language_changed)

        self._setup_products_table()
        self._apply_translations()

    def _on_language_changed(self, language: str) -> None:
        _ = language
        self._apply_translations()

    def _apply_translations(self) -> None:
        """
        Apply localized texts to the inventory header and controls.
        """
        self.setWindowTitle(self._translator["inventory.page_title"])
        self.btnAddProduct.setText(self._translator["inventory.add_product"])
        self.txtSearchProduct.setPlaceholderText(
            self._translator["inventory.search_placeholder"]
        )
        self._setup_products_table()

    def _setup_products_table(self) -> None:
        headers = [
            self._translator["inventory.table.column.id"],
            self._translator["inventory.table.column.name"],
            self._translator["inventory.table.column.barcode"],
            self._translator["inventory.table.column.stock"],
            self._translator["inventory.table.column.price"],
        ]
        self.tblProducts.setColumnCount(len(headers))
        self.tblProducts.setHorizontalHeaderLabels(headers)

        self.tblProducts.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tblProducts.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tblProducts.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        if self.tblProducts.verticalHeader() is not None:
            self.tblProducts.verticalHeader().setVisible(False)

        if self.tblProducts.horizontalHeader() is not None:
            self.tblProducts.horizontalHeader().setStretchLastSection(True)