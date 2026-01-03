from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.translation_manager import TranslationManager
from app.database import SessionLocal
from app.models.models import Customer
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CustomersDialog(QDialog):
    """
    Simple customer management and selection dialog.
    Provides search, basic CRUD, and allows selecting a customer for POS.
    """

    def __init__(
        self,
        translator: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._selected_customer: Optional[Dict[str, Any]] = None

        self._build_ui()
        self._connect_signals()
        self._apply_translations()
        self._load_customers()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.setModal(True)
        self.setMinimumSize(640, 420)

        if getattr(self._translator, "language", "en") == "fa":
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.lblTitle = QLabel(self)
        layout.addWidget(self.lblTitle)

        search_row = QHBoxLayout()
        self.txtSearch = QLineEdit(self)
        self.btnAdd = QPushButton(self)
        self.btnEdit = QPushButton(self)
        self.btnDelete = QPushButton(self)
        search_row.addWidget(self.txtSearch)
        search_row.addWidget(self.btnAdd)
        search_row.addWidget(self.btnEdit)
        search_row.addWidget(self.btnDelete)
        layout.addLayout(search_row)

        self.tblCustomers = QTableWidget(self)
        self.tblCustomers.setColumnCount(4)
        self.tblCustomers.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tblCustomers.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tblCustomers.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        header = self.tblCustomers.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        if self.tblCustomers.verticalHeader() is not None:
            self.tblCustomers.verticalHeader().setVisible(False)
        layout.addWidget(self.tblCustomers)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

    def _connect_signals(self) -> None:
        self.txtSearch.textChanged.connect(self._on_search_changed)
        self.btnAdd.clicked.connect(self._on_add_clicked)
        self.btnEdit.clicked.connect(self._on_edit_clicked)
        self.btnDelete.clicked.connect(self._on_delete_clicked)
        self.tblCustomers.doubleClicked.connect(lambda *_: self._on_accept())

    def _apply_translations(self) -> None:
        # Basic customer management texts
        self.setWindowTitle(self._translator.get("customers.dialog.title", "Customers"))
        self.lblTitle.setText(
            self._translator.get(
                "customers.dialog.subtitle", "Manage and select customers"
            )
        )
        self.txtSearch.setPlaceholderText(
            self._translator.get(
                "customers.search_placeholder",
                "Search by customer name or mobile...",
            )
        )
        self.btnAdd.setText(self._translator.get("customers.button.add", "Add"))
        self.btnEdit.setText(self._translator.get("customers.button.edit", "Edit"))
        self.btnDelete.setText(self._translator.get("customers.button.delete", "Delete"))
        
        headers = [
            self._translator.get("customers.table.column.id", "ID"),
            self._translator.get("customers.table.column.name", "Name"),
            self._translator.get("customers.table.column.mobile", "Mobile"),
            self._translator.get("customers.table.column.subscription", "Subscription Code"),
        ]
        self.tblCustomers.setHorizontalHeaderLabels(headers)

        # --- بخش جدید برای ترجمه دکمه‌های OK و Cancel ---
        if hasattr(self, "button_box"):
            btn_ok = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
            if btn_ok:
                # اگر این دیالوگ برای انتخاب است، بهتر است "انتخاب" باشد، در غیر این صورت "تأیید"
                btn_ok.setText(self._translator.get("dialog.button.select", "Select"))
            
            btn_cancel = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if btn_cancel:
                btn_cancel.setText(self._translator.get("dialog.button.cancel", "Cancel"))

    # ------------------------------------------------------------------ #
    # Data helpers
    # ------------------------------------------------------------------ #
    def _get_session(self) -> Session:
        return SessionLocal()

    def _load_customers(self) -> None:
        search_text = (self.txtSearch.text() or "").strip()
        with self._get_session() as session:
            query = session.query(Customer)
            if search_text:
                like = f"%{search_text}%"
                query = query.filter(
                    (Customer.FullName.ilike(like))
                    | (Customer.Phone.ilike(like))
                    | (Customer.SubscriptionCode.ilike(like))
                )
            customers: List[Customer] = query.order_by(Customer.FullName).all()

        self.tblCustomers.setRowCount(0)
        for row_idx, customer in enumerate(customers):
            self.tblCustomers.insertRow(row_idx)

            id_item = QTableWidgetItem(str(customer.CustID))
            id_item.setData(Qt.ItemDataRole.UserRole, int(customer.CustID))
            id_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )

            name_item = QTableWidgetItem(customer.FullName or "")
            mobile_item = QTableWidgetItem(customer.Phone or "")
            sub_item = QTableWidgetItem(customer.SubscriptionCode or "")

            self.tblCustomers.setItem(row_idx, 0, id_item)
            self.tblCustomers.setItem(row_idx, 1, name_item)
            self.tblCustomers.setItem(row_idx, 2, mobile_item)
            self.tblCustomers.setItem(row_idx, 3, sub_item)

    def _get_selected_row_data(self) -> Optional[Dict[str, Any]]:
        row = self.tblCustomers.currentRow()
        if row < 0:
            return None
        id_item = self.tblCustomers.item(row, 0)
        if id_item is None:
            return None
        cust_id = id_item.data(Qt.ItemDataRole.UserRole)
        if cust_id is None:
            try:
                cust_id = int(id_item.text())
            except (TypeError, ValueError):
                return None
        name_item = self.tblCustomers.item(row, 1)
        mobile_item = self.tblCustomers.item(row, 2)
        sub_item = self.tblCustomers.item(row, 3)
        return {
            "cust_id": int(cust_id),
            "name": name_item.text() if name_item else "",
            "mobile": mobile_item.text() if mobile_item else "",
            "subscription_code": sub_item.text() if sub_item else "",
        }

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_search_changed(self, text: str) -> None:
        _ = text
        self._load_customers()

    def _on_add_clicked(self) -> None:
        dialog = CustomerEditDialog(translator=self._translator, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_customers()

    def _on_edit_clicked(self) -> None:
        data = self._get_selected_row_data()
        if data is None:
            QMessageBox.information(
                self,
                self._translator.get("dialog.info_title", "Information"),
                self._translator.get(
                    "customers.dialog.info.select_customer",
                    "Please select a customer.",
                ),
            )
            return
        dialog = CustomerEditDialog(
            translator=self._translator,
            parent=self,
            customer_id=data["cust_id"],
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_customers()

    def _on_delete_clicked(self) -> None:
        data = self._get_selected_row_data()
        if data is None:
            QMessageBox.information(
                self,
                self._translator.get("dialog.info_title", "Information"),
                self._translator.get(
                    "customers.dialog.info.select_customer",
                    "Please select a customer.",
                ),
            )
            return
        reply = QMessageBox.question(
            self,
            self._translator.get("customers.dialog.delete.title", "Delete Customer"),
            self._translator.get(
                "customers.dialog.delete.body",
                "Are you sure you want to delete customer \"{label}\"?",
            ).format(label=data["name"] or data["mobile"]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        with self._get_session() as session:
            customer = session.get(Customer, data["cust_id"])
            if customer is None:
                return
            session.delete(customer)
            session.commit()
        self._load_customers()

    def _on_accept(self) -> None:
        data = self._get_selected_row_data()
        if data is None:
            QMessageBox.information(
                self, 
                self._translator.get("dialog.info_title", "Information"), 
                self._translator.get("customers.dialog.info.select_customer", "Please select a customer.")
            )
            return
        self._selected_customer = data
        self.accept()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def selected_customer(self) -> Optional[Dict[str, Any]]:
        return self._selected_customer

    @classmethod
    def select_customer(
        cls,
        translator: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> Optional[Tuple[int, str]]:
        dialog = cls(translator=translator, parent=parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        if dialog.selected_customer is None:
            return None
        data = dialog.selected_customer
        return int(data["cust_id"]), data["name"] or data["mobile"]


class CustomerEditDialog(QDialog):
    """
    Dialog to create or edit a single customer record.
    """

    def __init__(
        self,
        translator: TranslationManager,
        parent: Optional[QWidget] = None,
        customer_id: Optional[int] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._customer_id = customer_id

        self._build_ui()
        self._apply_translations()

        if self._customer_id is not None:
            self._load_customer()

    def _get_session(self) -> Session:
        return SessionLocal()

    def _build_ui(self) -> None:
        self.setModal(True)

        if getattr(self._translator, "language", "en") == "fa":
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.lblTitle = QLabel(self)
        layout.addWidget(self.lblTitle)

        form_layout = QVBoxLayout()
        self.txtName = QLineEdit(self)
        self.txtMobile = QLineEdit(self)
        self.txtSubscription = QLineEdit(self)

        self.lblName = QLabel(self)
        self.lblMobile = QLabel(self)
        self.lblSubscription = QLabel(self)

        form_layout.addWidget(self.lblName)
        form_layout.addWidget(self.txtName)
        form_layout.addWidget(self.lblMobile)
        form_layout.addWidget(self.txtMobile)
        form_layout.addWidget(self.lblSubscription)
        form_layout.addWidget(self.txtSubscription)
        layout.addLayout(form_layout)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        layout.addWidget(self.button_box)
        
        self.button_box.accepted.connect(self._on_save_clicked)
        self.button_box.rejected.connect(self.reject)

    def _apply_translations(self) -> None:
        if self._customer_id is None:
            self.setWindowTitle(
                self._translator.get("customers.edit.add_title", "Add Customer")
            )
            self.lblTitle.setText(
                self._translator.get(
                    "customers.edit.add_subtitle", "Add new customer"
                )
            )
        else:
            self.setWindowTitle(
                self._translator.get("customers.edit.edit_title", "Edit Customer")
            )
            self.lblTitle.setText(
                self._translator.get(
                    "customers.edit.edit_subtitle", "Edit customer details"
                )
            )
        self.lblName.setText(
            self._translator.get("customers.edit.field.name", "Full Name:")
        )
        self.lblMobile.setText(
            self._translator.get("customers.edit.field.mobile", "Mobile:")
        )
        self.lblSubscription.setText(
            self._translator.get(
                "customers.edit.field.subscription", "Subscription Code:"
            )
        )

        # --- بخش جدید برای ترجمه دکمه‌های Save و Cancel ---
        if hasattr(self, "button_box"):
            btn_save = self.button_box.button(QDialogButtonBox.StandardButton.Save)
            if btn_save:
                # استفاده از کلید عمومی ذخیره
                btn_save.setText(self._translator.get("inventory.dialog.button.save", "Save"))
            
            btn_cancel = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if btn_cancel:
                # استفاده از کلید عمومی انصراف
                btn_cancel.setText(self._translator.get("inventory.dialog.button.cancel", "Cancel"))
    
    
    def _load_customer(self) -> None:
        with self._get_session() as session:
            customer = session.get(Customer, self._customer_id)
            if customer is None:
                return
            self.txtName.setText(customer.FullName or "")
            self.txtMobile.setText(customer.Phone or "")
            self.txtSubscription.setText(customer.SubscriptionCode or "")

    def _on_save_clicked(self) -> None:
        name = (self.txtName.text() or "").strip()
        mobile = (self.txtMobile.text() or "").strip()
        subscription = (self.txtSubscription.text() or "").strip()

        if not name and not mobile:
            QMessageBox.warning(
                self,
                self._translator.get("dialog.error_title", "Error"),
                self._translator.get(
                    "customers.edit.error.name_or_mobile_required",
                    "At least one of name or mobile must be provided.",
                ),
            )
            return

        try:
            with self._get_session() as session:
                if self._customer_id is None:
                    customer = Customer(
                        FullName=name or None,
                        Phone=mobile or None,
                        SubscriptionCode=subscription or None,
                    )
                    session.add(customer)
                else:
                    customer = session.get(Customer, self._customer_id)
                    if customer is None:
                        QMessageBox.warning(
                            self,
                            self._translator.get("dialog.error_title", "Error"),
                            self._translator.get(
                                "customers.edit.error.not_found",
                                "Customer not found.",
                            ),
                        )
                        return
                    customer.FullName = name or None
                    customer.Phone = mobile or None
                    customer.SubscriptionCode = subscription or None
                    session.add(customer)
                session.commit()
        except Exception as e:
            logger.error("Error saving customer: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                self._translator.get("dialog.error_title", "Error"),
                str(e),
            )
            return

        self.accept()