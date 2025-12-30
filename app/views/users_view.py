from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.controllers.user_controller import UserController
from app.core.translation_manager import TranslationManager


class UsersView(QWidget):
    """
    Users management module.

    Displays a searchable table of users and exposes Add/Edit/Delete operations.
    """

    def __init__(
        self,
        translation_manager: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._translator = translation_manager
        self._controller = UserController()

        # The corresponding .ui file is expected at app/views/ui/users_view.ui
        # with at least:
        #   - QLineEdit  objectName="txtSearchUser"
        #   - QPushButton objectName="btnAddUser"
        #   - QPushButton objectName="btnEditUser"
        #   - QPushButton objectName="btnDeleteUser"
        #   - QTableWidget objectName="tblUsers"
        uic.loadUi("app/views/ui/users_view.ui", self)

        self._setup_table()
        self._connect_signals()
        self._apply_translations()
        self._load_users()

        self._translator.language_changed.connect(self._on_language_changed)

    # ------------------------------------------------------------------ #
    # UI helpers
    # ------------------------------------------------------------------ #
    def _setup_table(self) -> None:
        headers = [
            self._translator["users.table.column.id"],
            self._translator["users.table.column.full_name"],
            self._translator["users.table.column.username"],
            self._translator["users.table.column.role"],
            self._translator["users.table.column.mobile"],
            self._translator["users.table.column.status"],
        ]
        self.tblUsers.setColumnCount(len(headers))
        self.tblUsers.setHorizontalHeaderLabels(headers)

        self.tblUsers.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tblUsers.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tblUsers.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        if self.tblUsers.verticalHeader() is not None:
            self.tblUsers.verticalHeader().setVisible(False)

        if self.tblUsers.horizontalHeader() is not None:
            self.tblUsers.horizontalHeader().setStretchLastSection(True)

    def _connect_signals(self) -> None:
        self.txtSearchUser.textChanged.connect(self._on_search_changed)
        self.btnAddUser.clicked.connect(self._on_add_clicked)
        self.btnEditUser.clicked.connect(self._on_edit_clicked)
        self.btnDeleteUser.clicked.connect(self._on_delete_clicked)

    def _apply_translations(self) -> None:
        # Use the existing "Users" section key as the window title.
        self.setWindowTitle(self._translator["users.page_title"])
        self.btnAddUser.setText(self._translator["users.button.add"])
        self.btnEditUser.setText(self._translator["users.button.edit"])
        self.btnDeleteUser.setText(self._translator["users.button.delete"])
        self.txtSearchUser.setPlaceholderText(
            self._translator["inventory.search_placeholder"]
        )
        # Refresh headers to pick up translated text
        self._setup_table()

    # ------------------------------------------------------------------ #
    # Data loading
    # ------------------------------------------------------------------ #
    def _load_users(self) -> None:
        search_text = self.txtSearchUser.text().strip()
        users: List[Dict[str, Any]] = self._controller.list_users(
            search_text or None
        )

        self.tblUsers.setRowCount(0)

        for row_index, user in enumerate(users):
            self.tblUsers.insertRow(row_index)

            user_id = user.get("user_id")
            full_name = user.get("full_name", "")
            username = user.get("username", "")
            role = user.get("role", "")
            mobile = user.get("mobile", "")
            status = user.get("status", "")

            id_item = QTableWidgetItem(str(user_id))
            id_item.setData(Qt.ItemDataRole.UserRole, int(user_id))
            id_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )

            full_name_item = QTableWidgetItem(full_name)
            username_item = QTableWidgetItem(username)
            role_item = QTableWidgetItem(role)
            mobile_item = QTableWidgetItem(mobile)
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )

            self.tblUsers.setItem(row_index, 0, id_item)
            self.tblUsers.setItem(row_index, 1, full_name_item)
            self.tblUsers.setItem(row_index, 2, username_item)
            self.tblUsers.setItem(row_index, 3, role_item)
            self.tblUsers.setItem(row_index, 4, mobile_item)
            self.tblUsers.setItem(row_index, 5, status_item)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get_selected_user_id(self) -> Optional[int]:
        row = self.tblUsers.currentRow()
        if row < 0:
            return None

        item = self.tblUsers.item(row, 0)
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

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_language_changed(self, language: str) -> None:
        _ = language
        self._apply_translations()

    def _on_search_changed(self, text: str) -> None:
        _ = text
        self._load_users()

    def _on_add_clicked(self) -> None:
        dialog = UserDialog(
            translator=self._translator,
            controller=self._controller,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_users()

    def _on_edit_clicked(self) -> None:
        user_id = self._get_selected_user_id()
        if user_id is None:
            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator["users.dialog.error.select_edit"],
            )
            return

        user_data = self._controller.get_user(user_id)
        if user_data is None:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                self._translator["users.dialog.error.not_found"],
            )
            self._load_users()
            return

        dialog = UserDialog(
            translator=self._translator,
            controller=self._controller,
            parent=self,
            user_data=user_data,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_users()

    def _on_delete_clicked(self) -> None:
        user_id = self._get_selected_user_id()
        if user_id is None:
            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator["users.dialog.error.select_delete"],
            )
            return

        user_data = self._controller.get_user(user_id)
        if user_data is None:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                self._translator["users.dialog.error.not_found"],
            )
            self._load_users()
            return

        username = user_data.get("username", "")
        full_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        label = username or full_name or str(user_id)

        confirmation_text = self._translator["users.dialog.confirm_delete.body"].format(
            label=label
        )

        reply = QMessageBox.question(
            self,
            self._translator["users.dialog.confirm_delete.title"],
            confirmation_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._controller.delete_user(user_id)
        self._load_users()


class UserDialog(QDialog):
    """
    Dialog for creating or editing a user (Employee + UserAccount).
    """

    def __init__(
        self,
        translator: TranslationManager,
        controller: UserController,
        parent: Optional[QWidget] = None,
        user_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent)

        self._translator = translator
        self._controller = controller
        self._user_data = user_data

        self._build_ui()
        self._populate_roles()
        self._apply_translations()

        if self._user_data is not None:
            self._load_user_into_form(self._user_data)

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.lblTitle = QLabel(self)
        layout.addWidget(self.lblTitle)

        form_layout = QFormLayout()
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(8)

        self.txtFirstName = QLineEdit(self)
        self.txtLastName = QLineEdit(self)
        self.txtMobile = QLineEdit(self)
        self.txtUsername = QLineEdit(self)
        self.txtPassword = QLineEdit(self)
        self.txtPassword.setEchoMode(QLineEdit.EchoMode.Password)
        self.cmbRole = QComboBox(self)

        form_layout.addRow(
            self._translator["users.dialog.field.first_name"],
            self.txtFirstName,
        )
        form_layout.addRow(
            self._translator["users.dialog.field.last_name"],
            self.txtLastName,
        )
        form_layout.addRow(
            self._translator["users.dialog.field.mobile"],
            self.txtMobile,
        )
        form_layout.addRow(
            self._translator["users.dialog.field.username"],
            self.txtUsername,
        )
        form_layout.addRow(
            self._translator["users.dialog.field.password"],
            self.txtPassword,
        )
        form_layout.addRow(
            self._translator["users.dialog.field.role"],
            self.cmbRole,
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

    def _populate_roles(self) -> None:
        self.cmbRole.clear()
        roles = self._controller.list_roles()
        self.cmbRole.addItems(roles)

    def _apply_translations(self) -> None:
        self.setWindowTitle(self._translator["users.page_title"])
        if self._user_data is None:

            self.lblTitle.setText("Add new user")
        else:
            self.setWindowTitle(self._translator["sidebar.users"])
            self.lblTitle.setText("Edit user")

        self.btnSave.setText("Save")
        self.btnCancel.setText("Cancel")

    # ------------------------------------------------------------------ #
    # Data binding
    # ------------------------------------------------------------------ #
    def _load_user_into_form(self, user_data: Dict[str, Any]) -> None:
        self.txtFirstName.setText(user_data.get("first_name", ""))
        self.txtLastName.setText(user_data.get("last_name", ""))
        self.txtMobile.setText(user_data.get("mobile", ""))
        self.txtUsername.setText(user_data.get("username", ""))
        # Password is intentionally left blank for security; fill only when changing.

        role_title = user_data.get("role", "")
        if role_title:
            index = self.cmbRole.findText(role_title, Qt.MatchFlag.MatchExactly)
            if index >= 0:
                self.cmbRole.setCurrentIndex(index)
            else:
                # If the role does not yet exist in the combo, add it.
                self.cmbRole.addItem(role_title)
                self.cmbRole.setCurrentIndex(self.cmbRole.count() - 1)

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_save_clicked(self) -> None:
        first_name = self.txtFirstName.text().strip()
        last_name = self.txtLastName.text().strip()
        mobile = self.txtMobile.text().strip()
        username = self.txtUsername.text().strip()
        password = self.txtPassword.text()
        role_title = self.cmbRole.currentText().strip()

        if not first_name or not last_name or not mobile or not username or not role_title:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                "Please fill in all required fields.",
            )
            return

        # For new users, password is mandatory; for edits, it's optional.
        if self._user_data is None and not password:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                "Password is required for new users.",
            )
            return

        try:
            if self._user_data is None:
                self._controller.create_user(
                    first_name=first_name,
                    last_name=last_name,
                    mobile=mobile,
                    username=username,
                    password=password,
                    role_title=role_title,
                )
            else:
                user_id = int(self._user_data["user_id"])
                new_password = password or None
                self._controller.update_user(
                    user_id=user_id,
                    first_name=first_name,
                    last_name=last_name,
                    mobile=mobile,
                    username=username,
                    new_password=new_password,
                    role_title=role_title,
                )
        except ValueError as exc:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                str(exc),
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