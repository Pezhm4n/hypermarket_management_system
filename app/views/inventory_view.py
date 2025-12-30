from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

import jdatetime
from PyQt6 import uic
from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.inventory_controller import InventoryController
from app.core.translation_manager import TranslationManager


class InventoryView(QWidget):
    """
    Inventory management module.

    Displays a searchable table of products and exposes Add/Edit/Delete operations.
    """

    def __init__(
        self,
        translation_manager: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._translator = translation_manager
        self._controller = InventoryController()

        uic.loadUi("app/views/ui/inventory_view.ui", self)

        self._setup_table()
        self._connect_signals()
        self._apply_translations()
        self._load_products()

        self._translator.language_changed.connect(self._on_language_changed)

    def _setup_table(self) -> None:
        """
        Configure the products table headers and behavior.
        """
        headers = [
            self._translator["inventory.table.column.id"],
            self._translator["inventory.table.column.name"],
            self._translator["inventory.table.column.barcode"],
            self._translator["inventory.table.column.category"],
            self._translator["inventory.table.column.base_price"],
            self._translator["inventory.table.column.total_stock"],
            self._translator["inventory.table.column.min_stock"],
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

        header = self.tblProducts.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(0, 60)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

    def _connect_signals(self) -> None:
        """
        Connect UI signals to their respective slots.
        """
        self.txtSearchProduct.textChanged.connect(self._on_search_changed)
        self.btnAddProduct.clicked.connect(self._on_add_clicked)

        self.tblProducts.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tblProducts.customContextMenuRequested.connect(
            self._show_context_menu
        )

    def _apply_translations(self) -> None:
        """
        Apply localized texts to UI elements.
        """
        self.setWindowTitle(self._translator["inventory.page_title"])
        self.btnAddProduct.setText(self._translator["inventory.button.add"])
        self.txtSearchProduct.setPlaceholderText(
            self._translator["inventory.search_placeholder"]
        )
        self._setup_table()

    def _load_products(self) -> None:
        """
        Load products from the database and populate the table.
        """
        search_text = self.txtSearchProduct.text().strip()
        products: List[Dict[str, Any]] = self._controller.list_products(
            search_text or None
        )

        self.tblProducts.setRowCount(0)

        for row_index, product in enumerate(products):
            self.tblProducts.insertRow(row_index)

            prod_id = product.get("prod_id")
            name = product.get("name", "")
            barcode = product.get("barcode", "")
            category = product.get("category", "")
            base_price = product.get("base_price", Decimal("0"))
            total_stock = product.get("total_stock", Decimal("0"))
            min_stock = product.get("min_stock", 0)

            id_item = QTableWidgetItem(str(prod_id))
            id_item.setData(Qt.ItemDataRole.UserRole, int(prod_id))
            id_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )

            name_item = QTableWidgetItem(name)
            barcode_item = QTableWidgetItem(barcode)
            category_item = QTableWidgetItem(category)

            base_price_value = float(base_price)
            base_price_item = QTableWidgetItem(f"{base_price_value:,.0f}")
            base_price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            total_stock_value = float(total_stock)
            total_stock_item = QTableWidgetItem(f"{total_stock_value:,.0f}")
            total_stock_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )

            min_stock_item = QTableWidgetItem(str(min_stock))
            min_stock_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )

            self.tblProducts.setItem(row_index, 0, id_item)
            self.tblProducts.setItem(row_index, 1, name_item)
            self.tblProducts.setItem(row_index, 2, barcode_item)
            self.tblProducts.setItem(row_index, 3, category_item)
            self.tblProducts.setItem(row_index, 4, base_price_item)
            self.tblProducts.setItem(row_index, 5, total_stock_item)
            self.tblProducts.setItem(row_index, 6, min_stock_item)

    def _get_selected_product_id(self) -> Optional[int]:
        """
        Get the ProdID of the currently selected row in the table.
        """
        row = self.tblProducts.currentRow()
        if row < 0:
            return None

        item = self.tblProducts.item(row, 0)
        if item is None:
            return None

        value = item.data(Qt.ItemDataRole.UserRole)
        if value is None:
            try:
                value = int(item.text())
            except (TypeError, ValueError):
                return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _on_language_changed(self, language: str) -> None:
        """
        Handle language change event.
        """
        _ = language
        self._apply_translations()

    def _on_search_changed(self, text: str) -> None:
        """
        Handle search text change event.
        """
        _ = text
        self._load_products()

    def _on_add_clicked(self) -> None:
        """
        Handle Add Product button click.
        """
        dialog = ProductDialog(
            translator=self._translator,
            controller=self._controller,
            product_data=None,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_products()

    def _show_context_menu(self, pos) -> None:
        """
        Show context menu for the products table.
        """
        index = self.tblProducts.indexAt(pos)
        if not index.isValid():
            return

        row = index.row()
        if row < 0:
            return

        self.tblProducts.selectRow(row)

        id_item = self.tblProducts.item(row, 0)
        name_item = self.tblProducts.item(row, 1)
        barcode_item = self.tblProducts.item(row, 2)

        if id_item is None:
            return

        prod_id_data = id_item.data(Qt.ItemDataRole.UserRole)
        try:
            prod_id = int(
                prod_id_data if prod_id_data is not None else id_item.text()
            )
        except (TypeError, ValueError):
            return

        name = ""
        if name_item is not None and name_item.text():
            name = name_item.text().strip()

        barcode = ""
        if barcode_item is not None and barcode_item.text():
            barcode = barcode_item.text().strip()

        menu = QMenu(self)
        action_edit = menu.addAction(
            self._translator["inventory.context.edit"]
        )
        action_delete = menu.addAction(
            self._translator["inventory.context.delete"]
        )
        menu.addSeparator()
        action_copy = menu.addAction(
            self._translator["inventory.context.copy_barcode"]
        )

        global_pos = self.tblProducts.viewport().mapToGlobal(pos)
        chosen_action = menu.exec(global_pos)

        if chosen_action == action_edit:
            self._edit_product(prod_id)
        elif chosen_action == action_delete:
            self._delete_product(prod_id, name)
        elif chosen_action == action_copy and barcode:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(barcode)
            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator["inventory.message.copied"],
            )

    def _edit_product(self, prod_id: int) -> None:
        product = self._controller.get_product(prod_id)
        if not product:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                self._translator["inventory.dialog.error.not_found"],
            )
            self._load_products()
            return

        dialog = ProductDialog(
            translator=self._translator,
            controller=self._controller,
            product_data=product,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_products()

    def _delete_product(self, prod_id: int, label: str) -> None:
        if not label:
            label = str(prod_id)

        answer = QMessageBox.question(
            self,
            self._translator["inventory.dialog.confirm_delete.title"],
            self._translator["inventory.dialog.confirm_delete.body"].format(
                label=label
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._controller.delete_product(prod_id)
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )
            return

        self._load_products()


class ProductDialog(QDialog):
    """
    Dialog for creating or editing a product with initial inventory batch.
    """

    def __init__(
        self,
        translator: TranslationManager,
        controller: InventoryController,
        product_data: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._translator = translator
        self._controller = controller
        self._product_data: Optional[Dict[str, Any]] = product_data
        self._is_edit_mode: bool = self._product_data is not None
        self._product_id: Optional[int] = None
        if self._is_edit_mode and self._product_data is not None:
            try:
                self._product_id = int(self._product_data.get("prod_id"))
            except Exception:
                self._product_id = None

        self._build_ui()
        self._populate_categories()
        self._apply_translations()
        self._load_from_product()

    def _build_ui(self) -> None:
        """
        Construct the dialog UI programmatically.
        """
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.lblTitle = QLabel(self)
        layout.addWidget(self.lblTitle)

        form_layout = QFormLayout()
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(8)
        form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        self.txtName = QLineEdit(self)
        self.txtBarcode = QLineEdit(self)
        self.cmbCategory = QComboBox(self)

        self.spinBasePrice = QDoubleSpinBox(self)
        self.spinBasePrice.setRange(0, 9999999999.0)
        self.spinBasePrice.setDecimals(0)
        self.spinBasePrice.setGroupSeparatorShown(True)
        self.spinBasePrice.setSuffix(" ")

        self.spinMinStock = QSpinBox(self)
        self.spinMinStock.setRange(0, 9999999)

        self.chkPerishable = QCheckBox(self)

        self.spinInitialQty = QDoubleSpinBox(self)
        self.spinInitialQty.setRange(0, 9999999999.0)
        self.spinInitialQty.setDecimals(3)
        self.spinInitialQty.setGroupSeparatorShown(True)

        self.spinBuyPrice = QDoubleSpinBox(self)
        self.spinBuyPrice.setRange(0, 9999999999.0)
        self.spinBuyPrice.setDecimals(0)
        self.spinBuyPrice.setGroupSeparatorShown(True)
        self.spinBuyPrice.setSuffix(" ")

        self.dateExpiry = QLineEdit(self)
        self.dateExpiry.setInputMask("0000/00/00;_")
        jalali_today = jdatetime.date.today()
        self.dateExpiry.setText(jalali_today.strftime("%Y/%m/%d"))
        self.dateExpiry.setEnabled(False)

        barcode_regex = QRegularExpression(r"[A-Za-z0-9]{0,50}")
        self.txtBarcode.setValidator(
            QRegularExpressionValidator(barcode_regex, self)
        )

        form_layout.addRow(
            self._translator["inventory.dialog.field.name"],
            self.txtName,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.barcode"],
            self.txtBarcode,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.category"],
            self.cmbCategory,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.base_price"],
            self.spinBasePrice,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.min_stock"],
            self.spinMinStock,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.is_perishable"],
            self.chkPerishable,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.initial_quantity"],
            self.spinInitialQty,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.buy_price"],
            self.spinBuyPrice,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.expiry_date"],
            self.dateExpiry,
        )

        layout.addLayout(form_layout)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.btnSave = QPushButton(self)
        self.btnCancel = QPushButton(self)

        button_row.addWidget(self.btnSave)
        button_row.addWidget(self.btnCancel)

        layout.addLayout(button_row)

        self.btnSave.clicked.connect(self._on_save_clicked)
        self.btnCancel.clicked.connect(self.reject)

        self.chkPerishable.stateChanged.connect(self._on_perishable_changed)

    def _load_from_product(self) -> None:
        """
        Populate fields when editing an existing product.
        """
        if not self._is_edit_mode or not self._product_data:
            return

        self.lblTitle.setText(self._translator["inventory.dialog.edit_title"])

        self.txtName.setText(self._product_data.get("name", ""))
        self.txtBarcode.setText(self._product_data.get("barcode", ""))

        category = self._product_data.get("category", "")
        if category:
            index = self.cmbCategory.findText(category)
            if index != -1:
                self.cmbCategory.setCurrentIndex(index)

        base_price = self._product_data.get("base_price")
        if base_price is not None:
            try:
                self.spinBasePrice.setValue(float(base_price))
            except Exception:
                pass

        min_stock = self._product_data.get("min_stock")
        if min_stock is not None:
            try:
                self.spinMinStock.setValue(int(min_stock))
            except Exception:
                pass

        is_perishable = bool(self._product_data.get("is_perishable"))
        self.chkPerishable.setChecked(is_perishable)

    def _populate_categories(self) -> None:
        """
        Load categories from the controller and populate the combo box.
        """
        self.cmbCategory.clear()
        categories = self._controller.list_categories()
        self.cmbCategory.addItems(categories)

    def _apply_translations(self) -> None:
        """
        Apply localized texts to dialog elements.
        """
        self.setWindowTitle(self._translator["inventory.page_title"])
        if self._is_edit_mode:
            self.lblTitle.setText(self._translator["inventory.dialog.edit_title"])
        else:
            self.lblTitle.setText(self._translator["inventory.dialog.add_title"])
        self.btnSave.setText(self._translator["inventory.dialog.button.save"])
        self.btnCancel.setText(self._translator["inventory.dialog.button.cancel"])

    def _on_perishable_changed(self, state: int) -> None:
        """
        Enable or disable expiry date field based on perishable checkbox.
        """
        enabled = state == Qt.CheckState.Checked.value
        self.dateExpiry.setEnabled(enabled)
        if enabled:
            text = self.dateExpiry.text().strip()
            if not text or "_" in text:
                jalali_today = jdatetime.date.today()
                self.dateExpiry.setText(jalali_today.strftime("%Y/%m/%d"))
        else:
            self.dateExpiry.clear()

    def _on_save_clicked(self) -> None:
        """
        Validate input and create the product.
        """
        name = self.txtName.text().strip()
        barcode = self.txtBarcode.text().strip()
        category = self.cmbCategory.currentText().strip()
        base_price = self.spinBasePrice.value()
        min_stock = self.spinMinStock.value()
        is_perishable = self.chkPerishable.isChecked()
        initial_qty = self.spinInitialQty.value()
        buy_price = self.spinBuyPrice.value()

        if not name or not barcode or not category:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                self._translator["inventory.dialog.error.required_fields"],
            )
            return

        expiry_date_jalali: Optional[str] = None
        if not self._is_edit_mode and is_perishable:
            expiry_text = self.dateExpiry.text().strip()
            if not expiry_text or "_" in expiry_text:
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator["inventory.dialog.error.invalid_date"],
                )
                return
            expiry_date_jalali = expiry_text

        try:
            if self._is_edit_mode and self._product_id is not None:
                self._controller.update_product(
                    prod_id=self._product_id,
                    name=name,
                    barcode=barcode,
                    category_name=category,
                    base_price=base_price,
                    min_stock=min_stock,
                    is_perishable=is_perishable,
                )
            else:
                self._controller.create_product(
                    name=name,
                    barcode=barcode,
                    category_name=category,
                    base_price=base_price,
                    min_stock=min_stock,
                    is_perishable=is_perishable,
                    initial_quantity=initial_qty,
                    buy_price=buy_price,
                    expiry_date_jalali=expiry_date_jalali,
                )
        except ValueError as exc:
            message = str(exc)
            if message == "INVALID_JALALI_DATE":
                message = self._translator["inventory.dialog.error.invalid_date"]
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                message,
            )
            return
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )
            return

        self.accept()