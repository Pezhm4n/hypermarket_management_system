from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QDialog, QFormLayout, QDialogButtonBox
)
from app.controllers.supplier_controller import SupplierController
from app.core.translation_manager import TranslationManager

logger = logging.getLogger(__name__)

class SupplierDialog(QDialog):
    """دیالوگ برای افزودن یا ویرایش تأمین‌کننده"""
    def __init__(self, translator: TranslationManager, supplier_data: Optional[Dict] = None, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._data = supplier_data
        self.setModal(True)
        self.setMinimumWidth(350)
        self.setWindowTitle(self._translator.get("suppliers.dialog.title", "Supplier Details"))
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.txtName = QLineEdit(self)
        self.txtContact = QLineEdit(self)
        self.txtPhone = QLineEdit(self)
        self.txtEmail = QLineEdit(self)
        self.txtCity = QLineEdit(self)
        self.txtStreet = QLineEdit(self)

        form.addRow(self._translator.get("suppliers.field.company_name", "Company Name:"), self.txtName)
        form.addRow(self._translator.get("suppliers.field.contact", "Contact Person:"), self.txtContact)
        form.addRow(self._translator.get("suppliers.field.phone", "Phone:"), self.txtPhone)
        form.addRow(self._translator.get("suppliers.field.email", "Email:"), self.txtEmail)
        form.addRow(self._translator.get("suppliers.field.city", "City:"), self.txtCity)
        form.addRow(self._translator.get("suppliers.field.street", "Street:"), self.txtStreet)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if self._data:
            self.txtName.setText(self._data.get("company_name", ""))
            self.txtContact.setText(self._data.get("contact_person", ""))
            self.txtPhone.setText(self._data.get("phone", ""))
            self.txtEmail.setText(self._data.get("email", ""))
            self.txtCity.setText(self._data.get("city", ""))
            self.txtStreet.setText(self._data.get("street", ""))

    def get_values(self) -> Dict[str, str]:
        return {
            "name": self.txtName.text().strip(),
            "phone": self.txtPhone.text().strip(),
            "contact": self.txtContact.text().strip(),
            "email": self.txtEmail.text().strip(),
            "city": self.txtCity.text().strip(),
            "street": self.txtStreet.text().strip(),
        }

class SuppliersView(QWidget):
    def __init__(self, translation_manager: TranslationManager, parent=None):
        super().__init__(parent)
        self._translator = translation_manager
        self._controller = SupplierController()

        self._setup_ui()
        self._load_data()

        # react to language changes
        try:
            self._translator.language_changed.connect(self._on_language_changed)
        except Exception:
            logger.debug("Failed to connect SuppliersView to language_changed signal", exc_info=True)
        self._apply_translations()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ردیف بالا: دکمه افزودن و جستجو
        top_layout = QHBoxLayout()
        self.btnAddSupplier = QPushButton(self)
        self.btnAddSupplier.clicked.connect(self._on_add_clicked)

        self.txtSearch = QLineEdit(self)
        self.txtSearch.textChanged.connect(self._load_data)

        top_layout.addWidget(self.btnAddSupplier)
        top_layout.addStretch()
        top_layout.addWidget(self.txtSearch)
        layout.addLayout(top_layout)

        # جدول
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def _apply_translations(self) -> None:
        """Apply localized texts to suppliers page widgets."""
        try:
            self.btnAddSupplier.setText(
                self._translator.get("suppliers.button.add", "Add Supplier")
            )
            self.txtSearch.setPlaceholderText(
                self._translator.get("suppliers.search_placeholder", "Search suppliers...")
            )
            headers = [
                self._translator.get("suppliers.table.column.id", "ID"),
                self._translator.get("suppliers.table.column.name", "Company Name"),
                self._translator.get("suppliers.table.column.contact", "Contact Person"),
                self._translator.get("suppliers.table.column.phone", "Phone"),
                self._translator.get("suppliers.table.column.actions", "Actions"),
            ]
            self.table.setHorizontalHeaderLabels(headers)
        except Exception as e:
            logger.error("Error applying translations in SuppliersView: %s", e, exc_info=True)

    def _on_language_changed(self, language: str) -> None:
        _ = language
        self._apply_translations()

    def _load_data(self):
        search_text = self.txtSearch.text()
        suppliers = self._controller.list_suppliers(search_text)
        self.table.setRowCount(0)
        for row, s in enumerate(suppliers):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(s["sup_id"])))
            self.table.setItem(row, 1, QTableWidgetItem(s["company_name"]))
            self.table.setItem(row, 2, QTableWidgetItem(s["contact_person"]))
            self.table.setItem(row, 3, QTableWidgetItem(s["phone"]))
            
            # دکمه‌های عملیات
            btn_layout = QHBoxLayout()
            btn_edit = QPushButton("✎")
            btn_edit.setFixedWidth(30)
            btn_edit.clicked.connect(lambda ch, sid=s["sup_id"]: self._on_edit_clicked(sid))
            layout_widget = QWidget()
            btn_hbox = QHBoxLayout(layout_widget)
            btn_hbox.addWidget(btn_edit)
            btn_hbox.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 4, layout_widget)

    def _on_add_clicked(self):
        dialog = SupplierDialog(self._translator, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            vals = dialog.get_values()
            if not vals["name"] or not vals["phone"]:
                QMessageBox.warning(
                    self,
                    self._translator.get("dialog.warning_title", "Warning"),
                    self._translator.get(
                        "suppliers.dialog.error.name_phone_required",
                        "Name and Phone are required.",
                    ),
                )
                return
            self._controller.create_supplier(**vals)
            self._load_data()

    def _on_edit_clicked(self, sup_id):
        # پیدا کردن داده فعلی (در دنیای واقعی بهتر است از کنترلر یک متد get_supplier بگیرید)
        # فعلاً برای سادگی از دیتای جدول استفاده می‌کنیم یا کل لیست را فیلتر می‌کنیم
        suppliers = self._controller.list_suppliers()
        current_sup = next((s for s in suppliers if s["sup_id"] == sup_id), None)
        
        dialog = SupplierDialog(self._translator, supplier_data=current_sup, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._controller.update_supplier(sup_id, **dialog.get_values())
            self._load_data()
