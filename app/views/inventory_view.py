from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

import logging
import os
from datetime import date, timedelta, datetime
import jdatetime
import pandas as pd

logger = logging.getLogger(__name__)
from PyQt6 import uic
from app.utils import resource_path
from PyQt6.QtCore import Qt, QRegularExpression, QDate, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QRegularExpressionValidator, QColor, QBrush, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QTableWidget,
    QFileDialog
)

from app.controllers.inventory_controller import InventoryController
from app.core.barcode_manager import BarcodeGenerator
from app.core.irancode_scraper import IranCodeScraper
from app.core.translation_manager import TranslationManager
from app.views.components.scanner_dialog import ScannerDialog
from app.controllers.supplier_controller import SupplierController


class ProductLookupWorker(QThread):
    """
    Background worker that uses IranCodeScraper to query the official IranCode
    registry for a given barcode and emits the result back to the UI thread.
    """

    finished = pyqtSignal(str, object)  # barcode, info dict or None
    status_updated = pyqtSignal(str)  # human-readable status message

    def __init__(
        self,
        barcode: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._barcode = barcode

    def run(self) -> None:  # type: ignore[override]
        info = None

        def report_status(message: str) -> None:
            # Emit status updates for any connected UI (e.g., progress dialog).
            self.status_updated.emit(message)

        try:
            scraper = IranCodeScraper()
            info = scraper.fetch(self._barcode, status_callback=report_status)
        except Exception as exc:
            logger.exception(
                "Error in ProductLookupWorker (IranCode) for barcode %s: %s",
                self._barcode,
                exc,
            )
        # Emit even on failure so the dialog can clear its loading state.
        self.finished.emit(self._barcode, info)


class LookupProgressDialog(QDialog):
    """
    Modal dialog that shows progress and step-by-step status messages
    during an IranCode product lookup.
    """

    def __init__(
        self,
        translator: TranslationManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator

        self.setModal(True)
        self.setMinimumWidth(360)
        self.setWindowTitle(
            self._translator.get(
                "inventory.lookup.dialog.title",
                "استعلام ایران‌کد",
            )
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.lblStatus = QLabel(self)
        self.lblStatus.setWordWrap(True)
        layout.addWidget(self.lblStatus)

        self.progress = QProgressBar(self)
        # Indeterminate / busy indicator
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)

    def update_status(self, message: str) -> None:
        self.lblStatus.setText(message or "")

    def on_lookup_finished(self, *args: object) -> None:
        # Slot compatible with ProductLookupWorker.finished; simply closes dialog.
        self.accept()


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
        self._barcode_generator = BarcodeGenerator()
        self._read_only: bool = False

        uic.loadUi(resource_path("app/views/ui/inventory_view.ui"), self)

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

        self.btnImportExcel = QPushButton(self)
        self.btnImportExcel.setObjectName("btnImportExcel")
        self.horizontalLayout_top.insertWidget(2, self.btnImportExcel)
        self.btnImportExcel.clicked.connect(self._on_import_excel_clicked)

        self.btnExpiryReport.clicked.connect(self._open_expiry_report_dialog)
        self.btnInventoryReport.clicked.connect(self._open_inventory_report_dialog)
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

        self.btnImportExcel.setText(
            self._translator.get("inventory.button.import_excel", "ورود از اکسل")
        )

        self.btnExpiryReport.setText(
            self._translator.get(
                "inventory.button.expiry_report",
                "گزارش انقضا",
            )
        )
        self.btnInventoryReport.setText(
            self._translator.get(
                "inventory.button.inventory_report",
                "گزارش موجودی",
            )
        )

        self._setup_table()

    def refresh(self) -> None:
        """
        Public refresh method to reload products table.
        """
        try:
            self._load_products()
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.error("Error refreshing InventoryView: %s", exc, exc_info=True)

    def _load_products(self) -> None:
        """
        Load products from the database and populate the table with visual alerts.
        Highlights:
        - Red background for low stock (TotalStock < MinStock)
        """
        search_text = self.txtSearchProduct.text().strip()
        products: List[Dict[str, Any]] = self._controller.list_products(
            search_text or None
        )

        self.tblProducts.setRowCount(0)

        today = date.today()
        warning_date = today + timedelta(days=10)
        for row_index, product in enumerate(products):
            self.tblProducts.insertRow(row_index)

            prod_id = product.get("prod_id")
            name = product.get("name", "")
            barcode = product.get("barcode", "")
            category = product.get("category", "")
            base_price = product.get("base_price", Decimal("0"))
            total_stock = product.get("total_stock", Decimal("0"))
            min_stock = product.get("min_stock", Decimal("0"))
            next_expiry = product.get("next_expiry")

            # Teammate's Logic for Highlighting
            try:
                is_low_stock = total_stock < min_stock
            except Exception:
                is_low_stock = False

            is_near_expiry = False
            if next_expiry is not None:
                try:
                    if isinstance(next_expiry, datetime):
                        expiry_date = next_expiry.date()
                    else:
                        expiry_date = next_expiry
                    if isinstance(expiry_date, date):
                        is_near_expiry = expiry_date <= warning_date
                except Exception:
                    is_near_expiry = False

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

            highlight_brush = None
            if is_low_stock:
                low_stock_color = QColor(255, 100, 100, 100)  # Light Red
                highlight_brush = QBrush(low_stock_color)
            elif is_near_expiry:
                warn_color = QColor(255, 255, 150, 120)  # Light Yellow
                highlight_brush = QBrush(warn_color)

            if highlight_brush is not None:
                # Apply to all columns
                id_item.setBackground(highlight_brush)
                name_item.setBackground(highlight_brush)
                barcode_item.setBackground(highlight_brush)
                category_item.setBackground(highlight_brush)
                base_price_item.setBackground(highlight_brush)
                total_stock_item.setBackground(highlight_brush)
                min_stock_item.setBackground(highlight_brush)

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
        action_copy = menu.addAction(
            self._translator["inventory.context.copy_barcode"]
        )
        action_generate = menu.addAction(
            self._translator.get(
                "inventory.context.generate_barcode",
                "Generate Barcode",
            )
        )
        
        action_edit = None
        action_delete = None
        action_add_stock = None
        action_waste = None
        if not self._read_only:
            action_edit = menu.addAction(
                self._translator["inventory.context.edit"]
            )
            action_delete = menu.addAction(
                self._translator["inventory.context.delete"]
            )
            action_add_stock = menu.addAction(
                self._translator["inventory.context.add_stock"]
            )
            action_waste = menu.addAction(
                self._translator.get(
                    "inventory.context.record_waste",
                    "Record Waste",
                )
            )
        
        global_pos = self.tblProducts.viewport().mapToGlobal(pos)
        chosen_action = menu.exec(global_pos)
        
        if chosen_action == action_edit:
            self._edit_product(prod_id)
        elif chosen_action == action_delete:
            self._delete_product(prod_id, name)
        elif chosen_action == action_add_stock:
            self._open_restock_dialog(prod_id, name)
        elif chosen_action == action_waste:
            self._open_waste_dialog(prod_id, name)
        elif chosen_action == action_generate:
            code_value = barcode or str(prod_id)
            self._generate_barcode_image(code_value)
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
        if self._read_only:
            return

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

    def set_read_only(self, readonly: bool) -> None:
        """
        Enable or disable read-only mode for inventory operations.
        In read-only mode, Add/Edit/Delete operations are disabled.
        """
        self._read_only = bool(readonly)

        self.btnAddProduct.setEnabled(not self._read_only)
        self.btnAddProduct.setVisible(not self._read_only)

        self.btnExpiryReport.setEnabled(True)
        self.btnInventoryReport.setEnabled(True)

        # Context menu reacts to _read_only; no further action needed here.

    def _open_restock_dialog(self, prod_id: int, name: str) -> None:
        """
        Open dialog to add stock for a product, now including supplier selection.
        """
        try:
            dialog = RestockDialog(
                translator=self._translator,
                product_label=name,
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            qty, buy_price, expiry_date, sup_id = dialog.get_values()

            self._controller.add_stock(
                prod_id=prod_id,
                initial_qty=qty,
                buy_price=buy_price,
                expiry_date=expiry_date,
                sup_id=sup_id,
            )
            self._load_products()
        except Exception as exc:
            logger.exception("Error in _open_restock_dialog: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                self._translator["inventory.dialog.error.operation_failed"].format(
                    details=str(exc)
                ),
            )

    def _open_waste_dialog(self, prod_id: int, name: str) -> None:
        """
        Open dialog to record waste/damage for a product.
        """
        try:
            product = self._controller.get_product(prod_id)
            max_qty: Optional[Decimal] = None
            if product is not None:
                try:
                    max_qty = Decimal(
                        str(product.get("total_stock", Decimal("0")) or "0")
                    )
                except Exception:
                    max_qty = None

            dialog = WasteDialog(
                translator=self._translator,
                product_label=name,
                max_quantity=max_qty,
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            qty, reason, notes = dialog.get_values()

            window = self.window()
            user = getattr(window, "current_user", None) if window is not None else None
            emp_id = getattr(user, "EmpID", None) if user is not None else None

            self._controller.record_waste(
                prod_id=prod_id,
                quantity=qty,
                reason=reason,
                notes=notes,
                emp_id=emp_id,
            )

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator.get(
                    "inventory.waste.info.recorded",
                    "Waste recorded successfully.",
                ),
            )
            self._load_products()
        except ValueError as exc:
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                str(exc),
            )
        except Exception as exc:
            logger.exception("Error in _open_waste_dialog: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                self._translator["inventory.dialog.error.operation_failed"].format(
                    details=str(exc)
                ),
            )

    def _generate_barcode_image(self, code: str) -> None:
        """
        Generate a barcode PNG for the given code and open it with the
        system's default image viewer.
        """
        if not code:
            QMessageBox.warning(
                self,
                self._translator.get("dialog.warning_title", "Warning"),
                self._translator.get(
                    "inventory.dialog.error.no_barcode_for_product",
                    "This product does not have a barcode or ID to generate.",
                ),
            )
            return

        try:
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            barcodes_dir = os.path.join(app_dir, "barcodes")
            os.makedirs(barcodes_dir, exist_ok=True)

            safe_code = "".join(ch for ch in code if ch.isalnum()) or "barcode"
            target_path = os.path.join(barcodes_dir, f"{safe_code}.png")

            image_path = self._barcode_generator.generate(code, target_path)

            url = QUrl.fromLocalFile(image_path)
            if not QDesktopServices.openUrl(url):
                QMessageBox.information(
                    self,
                    self._translator.get("dialog.info_title", "Information"),
                    self._translator.get(
                        "inventory.dialog.info.barcode_saved",
                        "Barcode image saved at: {path}",
                    ).format(path=image_path),
                )
        except Exception as exc:
            logger.exception("Error generating barcode image: %s", exc)
            QMessageBox.critical(
                self,
                self._translator.get("dialog.error_title", "Error"),
                self._translator.get(
                    "inventory.dialog.error.barcode_generate_failed",
                    "Failed to generate barcode image: {details}",
                ).format(details=str(exc)),
            )

    def _open_expiry_report_dialog(self) -> None:
        """
        Open the expiry report dialog.
        """
        try:
            dialog = ExpiryReportDialog(
                translator=self._translator,
                controller=self._controller,
                parent=self,
            )
            dialog.exec()
        except Exception as exc:
            logger.exception("Error opening expiry report dialog: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )

    def _open_inventory_report_dialog(self) -> None:
        """
        Open the inventory report dialog.
        """
        try:
            dialog = InventoryReportDialog(
                translator=self._translator,
                controller=self._controller,
                parent=self,
            )
            dialog.exec()
        except Exception as exc:
            logger.exception("Error opening inventory report dialog: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )

    def _on_import_excel_clicked(self) -> None:
        """باز کردن پنجره انتخاب فایل و ارسال داده‌ها به کنترلر"""
        import pandas as pd
        
        # ۱. انتخاب فایل توسط کاربر
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.get("excel.dialog.select_file", "انتخاب فایل اکسل"),
            "",
            self._translator.get(
                "excel.dialog.file_filter",
                "Excel Files (*.xlsx *.xls)",
            ),
        )
        
        if not file_path:
            return

        try:
            # ۲. خواندن فایل با کتابخانه pandas
            df = pd.read_excel(file_path)
            
            # ۳. استانداردسازی نام ستون‌ها (فارسی یا انگلیسی فرقی نکند)
            column_mapping = {
                "نام کالا": "Name", "Name": "Name",
                "بارکد": "Barcode", "Barcode": "Barcode",
                "دسته‌بندی": "Category", "Category": "Category",
                "قیمت فروش": "BasePrice", "BasePrice": "BasePrice",
                "حداقل موجودی": "MinStock", "MinStock": "MinStock",
                "واحد": "Unit", "Unit": "Unit",
                "فاسد شدنی": "IsPerishable", "IsPerishable": "IsPerishable",
                "تعداد اولیه": "InitialQty", "InitialQty": "InitialQty",
                "قیمت خرید": "BuyPrice", "BuyPrice": "BuyPrice",
                "تاریخ انقضا": "ExpiryDate", "ExpiryDate": "ExpiryDate",
                "تامین کننده": "SupplierName", "SupplierName": "SupplierName"
            }
            df.rename(columns=column_mapping, inplace=True)
            
            # تبدیل داده‌های اکسل به لیست دیکشنری برای پایتون
            data_list = df.to_dict(orient="records")
            
            # ۴. ارسال به کنترلر برای ذخیره در دیتابیس
            result = self._controller.bulk_import_products(data_list)
            
            # ۵. نمایش نتیجه
            msg = self._translator.get("excel.success_msg", "تعداد {count} کالا وارد شد.").format(count=result['success'])
            if result['errors']:
                msg += "\n\n" + self._translator.get("excel.error_log", "خطاها:") + "\n" + "\n".join(result['errors'][:5])
            
            QMessageBox.information(self, self._translator.get("dialog.info_title", "Info"), msg)
            
            # رفرش جدول برای دیدن کالاهای جدید
            self._load_products()

        except Exception as e:
            logger.exception("Excel Import Error")
            QMessageBox.critical(
                self,
                self._translator.get("dialog.error_title", "Error"),
                self._translator.get(
                    "excel.error.read_failed",
                    "Failed to read Excel file: {error}",
                ).format(error=str(e)),
            )


class RestockDialog(QDialog):
    """
    Dialog for adding stock (creating a new inventory batch) for a product.
    Includes supplier selection.
    """
    def __init__(
        self,
        translator: TranslationManager,
        product_label: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._product_label = product_label
        
        # ✅ لود کردن کنترلر تأمین‌کنندگان
        from app.controllers.supplier_controller import SupplierController
        self._sup_controller = SupplierController()
        
        self._quantity = Decimal("0")
        self._buy_price = Decimal("0")
        self._expiry_date: Optional[date] = None
        self._selected_sup_id: Optional[int] = None # ذخیره آی‌دی تأمین‌کننده
        
        self._build_ui()
        self._load_suppliers() # پر کردن لیست تأمین‌کنندگان

    def _build_ui(self) -> None:
        self.setModal(True)
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel(self)
        try:
            caption = self._translator["inventory.dialog.restock_title"]
        except Exception:
            caption = "Add Stock"
        title.setText(f"{caption} - {self._product_label}")
        title.setWordWrap(True)
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.spinQuantity = QDoubleSpinBox(self)
        self.spinQuantity.setRange(0.0, 9999999999.0)
        self.spinQuantity.setDecimals(3)
        self.spinQuantity.setGroupSeparatorShown(True)

        self.spinBuyPrice = QDoubleSpinBox(self)
        self.spinBuyPrice.setRange(0.0, 9999999999.0)
        self.spinBuyPrice.setDecimals(0)
        self.spinBuyPrice.setGroupSeparatorShown(True)
        self.spinBuyPrice.setSuffix(" ")

        self.dateExpiry = QDateEdit(self)
        self.dateExpiry.setCalendarPopup(True)
        self.dateExpiry.setDate(QDate.currentDate())

        # ✅ اضافه کردن ComboBox تأمین‌کننده
        self.cmbSupplier = QComboBox(self)

        form.addRow(
            self._translator.get("inventory.restock.field.quantity", "Quantity"),
            self.spinQuantity,
        )
        form.addRow(
            self._translator.get("inventory.restock.field.buy_price", "Purchase Price"),
            self.spinBuyPrice,
        )
        form.addRow(
            self._translator.get("inventory.restock.field.expiry_date", "Expiry Date"),
            self.dateExpiry,
        )
        # ✅ اضافه شدن ردیف تأمین‌کننده به فرم
        form.addRow(
            self._translator.get("inventory.restock.field.supplier", "Supplier"),
            self.cmbSupplier,
        )

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        layout.addWidget(buttons)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

    def _load_suppliers(self) -> None:
        """بارگذاری لیست تأمین‌کنندگان از دیتابیس در ComboBox"""
        try:
            suppliers = self._sup_controller.list_suppliers()
            self.cmbSupplier.clear()
            # گزینه پیش‌فرض (بدون تأمین‌کننده)
            self.cmbSupplier.addItem("---", None) 
            for s in suppliers:
                self.cmbSupplier.addItem(s["company_name"], s["sup_id"])
        except Exception as exc:
            logger.error("Error loading suppliers in RestockDialog: %s", exc)

    def _on_accept(self) -> None:
        try:
            qty_val = self.spinQuantity.value()
            if qty_val <= 0:
                QMessageBox.warning(self, self._translator["dialog.warning_title"], 
                                    self._translator.get("inventory.dialog.error.invalid_quantity", "Invalid Qty"))
                return

            self._quantity = Decimal(str(qty_val))
            self._buy_price = Decimal(str(self.spinBuyPrice.value()))
            
            # ✅ دریافت آی‌دی تأمین‌کننده انتخاب شده
            self._selected_sup_id = self.cmbSupplier.currentData() 

            qdate = self.dateExpiry.date()
            self._expiry_date = date(qdate.year(), qdate.month(), qdate.day())
            self.accept()
        except Exception as exc:
            logger.exception("Error in RestockDialog._on_accept: %s", exc)
            QMessageBox.critical(self, self._translator["dialog.error_title"], str(exc))

    # ✅ آپدیت خروجی برای برگرداندن ۴ مقدار (شامل sup_id)
    def get_values(self) -> tuple[Decimal, Decimal, Optional[date], Optional[int]]:
        return self._quantity, self._buy_price, self._expiry_date, self._selected_sup_id



class WasteDialog(QDialog):
    """
    Dialog for recording waste/damage/theft adjustments.
    """

    def __init__(
        self,
        translator: TranslationManager,
        product_label: str,
        max_quantity: Optional[Decimal] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._product_label = product_label
        self._max_quantity = max_quantity
        self._quantity = Decimal("0")
        self._reason = ""
        self._notes = ""
        self._build_ui()

    def _build_ui(self) -> None:
        """
        Build the waste recording dialog UI.
        """
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel(self)
        try:
            caption = self._translator["inventory.waste.dialog_title"]
        except Exception:
            caption = "Record Waste"
        title.setText(f"{caption} - {self._product_label}")
        title.setWordWrap(True)
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.spinQuantity = QDoubleSpinBox(self)
        max_value = 9999999999.0
        if self._max_quantity is not None:
            try:
                mq = float(self._max_quantity)
                if mq > 0:
                    max_value = mq
            except Exception:
                pass
        self.spinQuantity.setRange(0.0, max_value)
        self.spinQuantity.setDecimals(3)
        self.spinQuantity.setGroupSeparatorShown(True)

        self.cmbReason = QComboBox(self)
        self.cmbReason.addItem(
            self._translator.get("inventory.waste.reason.breakage", "Breakage"),
            "Breakage",
        )
        self.cmbReason.addItem(
            self._translator.get("inventory.waste.reason.theft", "Theft"),
            "Theft",
        )
        self.cmbReason.addItem(
            self._translator.get("inventory.waste.reason.expiry", "Expired"),
            "Expiry",
        )
        self.cmbReason.addItem(
            self._translator.get("inventory.waste.reason.other", "Other"),
            "Other",
        )

        self.txtNotes = QLineEdit(self)
        self.txtNotes.setPlaceholderText(
            self._translator.get(
                "inventory.waste.notes_placeholder",
                "Optional notes...",
            )
        )

        form.addRow(
            self._translator.get("inventory.waste.field.quantity", "Quantity"),
            self.spinQuantity,
        )
        form.addRow(
            self._translator.get("inventory.waste.field.reason", "Reason"),
            self.cmbReason,
        )
        form.addRow(
            self._translator.get("inventory.waste.field.notes", "Notes"),
            self.txtNotes,
        )

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        layout.addWidget(buttons)

        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

    def _on_accept(self) -> None:
        """
        Validate and accept the dialog.
        """
        try:
            qty_val = self.spinQuantity.value()
            if qty_val <= 0:
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator.get(
                        "inventory.dialog.error.invalid_quantity",
                        "Quantity must be greater than zero.",
                    ),
                )
                return

            self._quantity = Decimal(str(qty_val))
            self._reason = self.cmbReason.currentData() or "Other"
            self._notes = self.txtNotes.text().strip()

            self.accept()
        except Exception as exc:
            logger.exception("Error in WasteDialog._on_accept: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )

    def get_values(self) -> tuple[Decimal, str, str]:
        """
        Return the entered values.
        """
        return self._quantity, self._reason, self._notes


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
        self._sup_controller = SupplierController()
        self._product_data: Optional[Dict[str, Any]] = product_data
        self._is_edit_mode: bool = self._product_data is not None
        self._product_id: Optional[int] = None
        if self._is_edit_mode and self._product_data is not None:
            try:
                self._product_id = int(self._product_data.get("prod_id"))
            except Exception:
                self._product_id = None

        # Helpers for optional IranCode-based product lookup when scanning a new product
        self._lookup_thread: Optional[ProductLookupWorker] = None
        self._original_name_placeholder: str = ""
        self._name_lookup_in_progress: bool = False
        self._last_lookup_manual: bool = False

        self._build_ui()
        self._load_suppliers()

        # Capture the initial placeholder text for the product name field so
        # we can restore it after showing a temporary "searching..." message.
        try:
            self._original_name_placeholder = self.txtName.placeholderText()
        except Exception:
            self._original_name_placeholder = ""

        self._populate_categories()
        self._apply_translations()
        self._load_from_product()

        # Placeholder for the lookup progress dialog (manual lookups)
        self._lookup_dialog: Optional[LookupProgressDialog] = None

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
        self.btnOnlineLookup = QPushButton(self)
        self.txtBarcode = QLineEdit(self)
        self.btnScanBarcode = QPushButton(self)
        self.cmbCategory = QComboBox(self)

        self.spinBasePrice = QDoubleSpinBox(self)
        self.spinBasePrice.setRange(0, 9999999999.0)
        self.spinBasePrice.setDecimals(0)
        self.spinBasePrice.setGroupSeparatorShown(True)
        self.spinBasePrice.setSuffix(" ")

        # Helper button to open Torob search for price lookup
        self.btnPriceLookup = QPushButton(self)

        self.spinMinStock = QDoubleSpinBox(self)
        self.spinMinStock.setRange(0, 9999999999.0)
        self.spinMinStock.setDecimals(3)
        self.spinMinStock.setGroupSeparatorShown(True)

        self.chkPerishable = QCheckBox(self)

        self.cmbSupplier = QComboBox(self)
        form_layout.addRow(
            self._translator.get("inventory.restock.field.supplier", "Supplier"),
            self.cmbSupplier,
        )

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

        self.cmbUnit = QComboBox(self)
        self.cmbUnit.addItem(
            self._translator.get("unit.pcs", "Piece"),
            "Pcs",
        )
        self.cmbUnit.addItem(
            self._translator.get("unit.kg", "Kilogram"),
            "Kg",
        )
        self.cmbUnit.addItem(
            self._translator.get("unit.liter", "Liter"),
            "Liter",
        )
        self.cmbUnit.addItem(
            self._translator.get("unit.meter", "Meter"),
            "Meter",
        )
        self.cmbUnit.addItem(
            self._translator.get("unit.pack", "Pack"),
            "Pack",
        )

        self.lblTotalStockDisplay = QLineEdit(self)
        self.lblTotalStockDisplay.setReadOnly(True)
        self.lblTotalStockDisplay.setEnabled(False)

        barcode_regex = QRegularExpression(r"[A-Za-z0-9]{0,50}")
        self.txtBarcode.setValidator(
            QRegularExpressionValidator(barcode_regex, self)
        )

        # Product name row with inline online lookup button
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(4)
        name_row.addWidget(self.txtName)

        self.btnOnlineLookup.setText("🔍")
        self.btnOnlineLookup.setFixedWidth(36)
        self.btnOnlineLookup.setToolTip(
            self._translator.get(
                "inventory.dialog.button.lookup_online",
                "Search product details online",
            )
        )
        name_row.addWidget(self.btnOnlineLookup)

        name_container = QWidget(self)
        name_container.setLayout(name_row)

        form_layout.addRow(
            self._translator["inventory.dialog.field.name"],
            name_container,
        )

        # Barcode row with inline scan button
        barcode_row = QHBoxLayout()
        barcode_row.setContentsMargins(0, 0, 0, 0)
        barcode_row.setSpacing(4)
        barcode_row.addWidget(self.txtBarcode)

        self.btnScanBarcode.setText("📷")
        self.btnScanBarcode.setFixedWidth(36)
        self.btnScanBarcode.setToolTip(
            self._translator.get(
                "inventory.dialog.button.scan",
                "Scan barcode",
            )
        )
        barcode_row.addWidget(self.btnScanBarcode)

        barcode_container = QWidget(self)
        barcode_container.setLayout(barcode_row)

        form_layout.addRow(
            self._translator["inventory.dialog.field.barcode"],
            barcode_container,
        )

        form_layout.addRow(
            self._translator["inventory.dialog.field.category"],
            self.cmbCategory,
        )
        # Base price row with inline Torob search button
        price_row = QHBoxLayout()
        price_row.setContentsMargins(0, 0, 0, 0)
        price_row.setSpacing(4)
        price_row.addWidget(self.spinBasePrice)

        self.btnPriceLookup.setText("🛒")
        self.btnPriceLookup.setFixedWidth(36)
        self.btnPriceLookup.setToolTip(
            self._translator.get(
                "inventory.dialog.button.lookup_price_torob",
                "Open Torob search for price",
            )
        )
        price_row.addWidget(self.btnPriceLookup)

        price_container = QWidget(self)
        price_container.setLayout(price_row)

        form_layout.addRow(
            self._translator["inventory.dialog.field.base_price"],
            price_container,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.min_stock"],
            self.spinMinStock,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.unit"],
            self.cmbUnit,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.current_stock"],
            self.lblTotalStockDisplay,
        )
        form_layout.addRow(
            self._translator["inventory.dialog.field.is_perishable"],
            self.chkPerishable,
        )

        # Batch-related fields (only needed when creating a new product)
        self.lblInitialQty = QLabel(
            self._translator["inventory.dialog.field.initial_quantity"]
        )
        form_layout.addRow(self.lblInitialQty, self.spinInitialQty)

        self.lblBuyPrice = QLabel(
            self._translator["inventory.dialog.field.buy_price"]
        )
        form_layout.addRow(self.lblBuyPrice, self.spinBuyPrice)

        self.lblExpiry = QLabel(
            self._translator["inventory.dialog.field.expiry_date"]
        )
        form_layout.addRow(self.lblExpiry, self.dateExpiry)

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
        self.btnScanBarcode.clicked.connect(self._on_scan_clicked)
        self.btnOnlineLookup.clicked.connect(self._on_lookup_clicked)
        self.btnPriceLookup.clicked.connect(self._on_price_lookup_clicked)
        self.chkPerishable.stateChanged.connect(self._on_perishable_changed)

    def _toggle_batch_fields(self, visible: bool) -> None:
        """Show or hide batch-related fields."""
        self.lblInitialQty.setVisible(visible)
        self.spinInitialQty.setVisible(visible)
        self.lblBuyPrice.setVisible(visible)
        self.spinBuyPrice.setVisible(visible)
        self.lblExpiry.setVisible(visible)
        self.dateExpiry.setVisible(visible)

    def _start_online_lookup_if_needed(self, barcode: str, manual: bool = False) -> None:
        """
        Start a background lookup to fetch a probable product name (and
        optionally category) from online sources.

        For automatic lookups (scanner), we first check whether the barcode
        already exists locally and skip online requests when it does.

        For manual lookups (triggered by the search button), we always allow
        the online request, regardless of local existence or edit/add mode.
        """
        try:
            code = (barcode or "").strip()
            if not code:
                return

            # For automatic lookups (e.g., from scanner), only auto-fill
            # information when creating a new product; editing an existing
            # product should not suddenly overwrite its fields.
            if not manual and self._is_edit_mode:
                return

            if not manual:
                # Automatic lookup: respect local DB existence and avoid
                # unnecessary web traffic.
                try:
                    exists = self._controller.has_product_with_barcode(code)
                except Exception as exc:
                    logger.exception(
                        "Error checking local product existence for barcode %s: %s",
                        code,
                        exc,
                    )
                    # Fail-safe: if we cannot check the DB, avoid spamming web lookups.
                    return

                if exists:
                    # Barcode is already registered locally; nothing to do.
                    return

            # Indicate to the user that a lookup is in progress, but only if
            # they have not already typed a name manually.
            try:
                if not self._name_lookup_in_progress:
                    self._name_lookup_in_progress = True
                    if not self.txtName.text().strip():
                        placeholder = self._translator.get(
                            "inventory.dialog.placeholder.searching_name",
                            "در حال جستجوی نام کالا...",
                        )
                        # Ensure we have the original placeholder stored
                        if not self._original_name_placeholder:
                            self._original_name_placeholder = (
                                self.txtName.placeholderText() or ""
                            )
                        self.txtName.setPlaceholderText(placeholder)
            except Exception:
                # Placeholder UX is best-effort; never break lookup on UI errors.
                pass

            worker = ProductLookupWorker(
                barcode=code,
                parent=self
            )
            self._lookup_thread = worker

            if manual:
                # For manual lookups, the caller is responsible for wiring up
                # status updates and the progress dialog. We only keep a
                # reference to the worker here.
                return

            worker.finished.connect(self._on_product_lookup_finished)
            worker.start()
        except Exception as exc:
            logger.exception(
                "Error starting online product lookup for barcode %s: %s",
                barcode,
                exc,
            )

    def _load_from_product(self) -> None:
        """
        Populate fields when editing an existing product.
        """
        if not self._is_edit_mode or not self._product_data:
            return

        self.blockSignals(True)
        try:
            # Hide batch fields in edit mode
            self._toggle_batch_fields(False)
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
                    self.spinMinStock.setValue(float(min_stock))
                except Exception:
                    pass

            total_stock = self._product_data.get("total_stock")
            if total_stock is not None:
                try:
                    self.lblTotalStockDisplay.setText(f"{float(total_stock):,.3f}")
                except Exception:
                    try:
                        self.lblTotalStockDisplay.setText(str(total_stock))
                    except Exception:
                        self.lblTotalStockDisplay.clear()

            unit_code = self._product_data.get("unit") or "Pcs"
            try:
                index = -1
                for i in range(self.cmbUnit.count()):
                    if self.cmbUnit.itemData(i) == unit_code:
                        index = i
                        break
                if index >= 0:
                    self.cmbUnit.setCurrentIndex(index)
            except Exception:
                pass

            is_perishable = bool(self._product_data.get("is_perishable"))
            self.chkPerishable.setChecked(is_perishable)
        finally:
            self.blockSignals(False)

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
        if hasattr(self, "btnScanBarcode"):
            self.btnScanBarcode.setToolTip(
                self._translator.get(
                    "inventory.dialog.button.scan",
                    "Scan barcode",
                )
            )
        if hasattr(self, "btnOnlineLookup"):
            self.btnOnlineLookup.setToolTip(
                self._translator.get(
                    "inventory.dialog.button.lookup_online",
                    "Search product details online",
                )
            )
        if hasattr(self, "btnPriceLookup"):
            self.btnPriceLookup.setToolTip(
                self._translator.get(
                    "inventory.dialog.button.lookup_price_torob",
                    "Open Torob search for price",
                )
            )

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

    def _on_lookup_clicked(self) -> None:
        """
        Trigger a manual online lookup for the current barcode with
        a modal progress dialog that shows step-by-step status updates.
        """
        try:
            code = (self.txtBarcode.text() or "").strip()
            if not code:
                QMessageBox.warning(
                    self,
                    self._translator.get("dialog.warning_title", "Warning"),
                    self._translator.get(
                        "inventory.dialog.error.no_barcode_for_lookup",
                        "Please enter a barcode before searching online.",
                    ),
                )
                return

            # Avoid starting multiple lookups in parallel.
            if self._lookup_thread is not None and self._lookup_thread.isRunning():
                QMessageBox.information(
                    self,
                    self._translator.get("dialog.info_title", "Information"),
                    self._translator.get(
                        "inventory.dialog.info.lookup_in_progress",
                        "An online lookup is already in progress.",
                    ),
                )
                return

            # Run the common validation / placeholder logic, but in manual mode.
            self._last_lookup_manual = True
            self._start_online_lookup_if_needed(code, manual=True)

            # If the lookup could not be started (e.g., barcode already exists),
            # _lookup_thread will still be None.
            if self._lookup_thread is None:
                self._last_lookup_manual = False
                return

            dialog = LookupProgressDialog(translator=self._translator, parent=self)
            self._lookup_dialog = dialog

            # Wire status updates and completion to the dialog and handler.
            self._lookup_thread.status_updated.connect(dialog.update_status)
            self._lookup_thread.finished.connect(self._on_lookup_worker_finished)
            self._lookup_thread.finished.connect(dialog.on_lookup_finished)

            # Initial status text
            dialog.update_status(
                self._translator.get(
                    "inventory.lookup.status.starting",
                    "Starting online lookup...",
                )
            )

            # Start the worker and show the modal dialog.
            self._lookup_thread.start()
            dialog.exec()
        except Exception as exc:
            logger.exception("Error in ProductDialog._on_lookup_clicked: %s", exc)
            QMessageBox.critical(
                self,
                self._translator.get("dialog.error_title", "Error"),
                str(exc),
            )

    def _on_price_lookup_clicked(self) -> None:
        """
        Open a Torob search in the system browser to help the user
        find a suitable price for the current product.
        """
        try:
            name = (self.txtName.text() or "").strip()
            barcode = (self.txtBarcode.text() or "").strip()

            if not name and not barcode:
                QMessageBox.information(
                    self,
                    self._translator.get("dialog.info_title", "Information"),
                    self._translator.get(
                        "inventory.dialog.info.no_term_for_price_lookup",
                        "Please enter a product name or barcode before opening Torob.",
                    ),
                )
                return

            search_term = name or barcode
            # Torob expects the search term under the "query" parameter.
            url = QUrl(f"https://torob.com/search/?query={search_term}")
            if not QDesktopServices.openUrl(url):
                QMessageBox.warning(
                    self,
                    self._translator.get("dialog.warning_title", "Warning"),
                    self._translator.get(
                        "inventory.dialog.error.torob_open_failed",
                        "Could not open Torob in your default browser.",
                    ),
                )
        except Exception as exc:
            logger.exception("Error in ProductDialog._on_price_lookup_clicked: %s", exc)
            QMessageBox.critical(
                self,
                self._translator.get("dialog.error_title", "Error"),
                str(exc),
            )

    def _on_scan_clicked(self) -> None:
        """
        Open the ScannerDialog and fill the barcode field with the result.
        """
        try:
            dialog = ScannerDialog(translator=self._translator, parent=self)
            dialog.barcode_detected.connect(self._on_scanner_barcode_detected)
            dialog.exec()
        except Exception as exc:
            logger.exception("Error in ProductDialog._on_scan_clicked: %s", exc)
            QMessageBox.critical(
                self,
                self._translator.get("dialog.error_title", "Error"),
                str(exc),
            )

    def _on_scanner_barcode_detected(self, code: str) -> None:
        """
        Handle barcode detected from the external scanner dialog.

        The barcode field is filled automatically. The user can then
        trigger an explicit online lookup using the search button next
        to the product name field.
        """
        try:
            if not code:
                return
            cleaned = code.strip()
            if not cleaned:
                return
            self.txtBarcode.setText(cleaned)
        except Exception as exc:
            logger.exception(
                "Error in ProductDialog._on_scanner_barcode_detected: %s", exc
            )

    def _on_lookup_worker_finished(self, barcode: str, info: object) -> None:
        """
        Wrapper for ProductLookupWorker.finished used by manual lookups.

        Closes the progress dialog (if any) and then applies the result
        using the shared _on_product_lookup_finished logic.
        """
        try:
            # Close progress dialog if it is open
            lookup_dialog = getattr(self, "_lookup_dialog", None)
            if lookup_dialog is not None:
                try:
                    lookup_dialog.accept()
                except Exception:
                    pass
                self._lookup_dialog = None
        except Exception:
            # Even if closing the dialog fails, we still want to apply results.
            pass

        self._on_product_lookup_finished(barcode, info)

    def _on_product_lookup_finished(self, barcode: str, info: object) -> None:
        """
        Handle completion of the background product lookup.

        The result is only applied if the barcode in the dialog still
        matches the looked-up barcode. Fetched values are allowed to
        overwrite existing user input (e.g., product name) so that
        authoritative data from IranCode takes precedence.
        """
        try:
            # Drop reference to the finished worker
            self._lookup_thread = None
            self._name_lookup_in_progress = False

            # Restore the original placeholder text on the name field
            try:
                self.txtName.setPlaceholderText(
                    getattr(self, "_original_name_placeholder", "")
                )
            except Exception:
                pass

            current_barcode = (self.txtBarcode.text() or "").strip()
            if not current_barcode or current_barcode != barcode:
                # User changed the barcode while the lookup was running; ignore.
                self._last_lookup_manual = False
                return

            if not isinstance(info, dict):
                # Manual lookup with no structured info: inform the user.
                if self._last_lookup_manual:
                    try:
                        QMessageBox.information(
                            self,
                            self._translator.get("dialog.info_title", "Information"),
                            self._translator.get(
                                "inventory.lookup.info.not_found",
                                "No product information could be found online for this barcode. "
                                "Please enter the product details manually.",
                            ),
                        )
                    except Exception:
                        pass
                self._last_lookup_manual = False
                return

            name = str(info.get("name", "") or "").strip()
            category = str(info.get("category", "") or "").strip()

            # Always apply the fetched name so that IranCode can overwrite
            # any previously typed value by the user.
            name_applied = False
            if name:
                self.txtName.setText(name)
                name_applied = True

            # Apply category only if it already exists in the current combo box
            # (case-insensitive match) and the user has not selected anything yet.
            if category:
                current_category = self.cmbCategory.currentText().strip()
                if not current_category:
                    target_lower = category.lower()
                    index = -1
                    for i in range(self.cmbCategory.count()):
                        item_text = (self.cmbCategory.itemText(i) or "").strip()
                        if item_text.lower() == target_lower:
                            index = i
                            break
                    if index >= 0:
                        self.cmbCategory.setCurrentIndex(index)

            # If lookup was manual and we still could not apply a name, notify the user.
            if self._last_lookup_manual and not name_applied:
                try:
                    QMessageBox.information(
                        self,
                        self._translator.get("dialog.info_title", "Information"),
                        self._translator.get(
                            "inventory.lookup.info.not_found",
                            "No product information could be found online for this barcode. "
                            "Please enter the product details manually.",
                        ),
                    )
                except Exception:
                    pass
            self._last_lookup_manual = False
        except Exception as exc:
            self._last_lookup_manual = False
            logger.exception(
                "Error applying fetched product info for barcode %s: %s",
                barcode,
                exc,
            )

    def _on_save_clicked(self) -> None:
        """
        Validate input and create the product.
        """
        name = self.txtName.text().strip()
        barcode = self.txtBarcode.text().strip()
        category = self.cmbCategory.currentText().strip()
        base_price = self.spinBasePrice.value()
        min_stock = self.spinMinStock.value()
        unit_code = self.cmbUnit.currentData() or "Pcs"
        is_perishable = self.chkPerishable.isChecked()
        initial_qty = self.spinInitialQty.value()
        buy_price = self.spinBuyPrice.value()
        sup_id = self.cmbSupplier.currentData()

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
                    unit=unit_code,
                    is_perishable=is_perishable,
                )
            else:
                self._controller.create_product(
                    name=name,
                    barcode=barcode,
                    category_name=category,
                    base_price=base_price,
                    min_stock=min_stock,
                    unit=unit_code,
                    is_perishable=is_perishable,
                    initial_quantity=initial_qty,
                    buy_price=buy_price,
                    expiry_date_jalali=expiry_date_jalali,
                    sup_id=sup_id,
                )
        except ValueError as exc:
            message = str(exc)
            if message == "INVALID_JALALI_DATE":
                message = self._translator["inventory.dialog.error.invalid_date"]
            logger.exception("Validation error while saving product: %s", exc)
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                message,
            )
            return
        except Exception as exc:
            logger.exception("Unexpected error while saving product: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                self._translator["inventory.dialog.error.operation_failed"].format(
                    details=str(exc)
                ),
            )
            return

        self.accept()
    
    def _load_suppliers(self) -> None:
        """بارگذاری لیست تامین‌کنندگان در کمبوباکس"""
        try:
            suppliers = self._sup_controller.list_suppliers()
            self.cmbSupplier.clear()
            self.cmbSupplier.addItem("---", None)
            for s in suppliers:
                self.cmbSupplier.addItem(s["company_name"], s["sup_id"])
        except Exception as exc:
            logger.error("Error loading suppliers: %s", exc)

class ExpiryReportDialog(QDialog):
    """
    Dialog for displaying products near expiry with filtering options.
    """

    def __init__(
        self,
        translator: TranslationManager,
        controller: InventoryController,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._controller = controller
        self._current_days = 30
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        self.setModal(True)
        self.setMinimumSize(800, 600)
        self.setWindowTitle(
            self._translator.get(
                "inventory.expiry_report.dialog.title",
                "Products Near Expiry Report",
            )
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Filter controls
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        lbl_days = QLabel(self)
        lbl_days.setText(
            self._translator.get(
                "inventory.expiry_report.field.days",
                "Show products expiring within days:",
            )
        )
        filter_layout.addWidget(lbl_days)

        self.spinDays = QSpinBox(self)
        self.spinDays.setRange(1, 365)
        self.spinDays.setValue(30)
        self.spinDays.setSuffix(
            self._translator.get("inventory.expiry_report.field.days_suffix", " days")
        )
        filter_layout.addWidget(self.spinDays)

        self.btnRefresh = QPushButton(self)
        self.btnRefresh.setText(
            self._translator.get(
                "inventory.expiry_report.button.refresh",
                "Refresh",
            )
        )
        filter_layout.addWidget(self.btnRefresh)

        filter_layout.addStretch()

        self.btnExportPDF = QPushButton(self)
        self.btnExportPDF.setText(
            self._translator.get(
                "inventory.expiry_report.button.export_pdf",
                "Export PDF",
            )
        )
        filter_layout.addWidget(self.btnExportPDF)

        layout.addLayout(filter_layout)

        # Table
        self.tblExpiry = QTableWidget(self)
        self.tblExpiry.setColumnCount(6)
        self.tblExpiry.setHorizontalHeaderLabels(
            [
                self._translator.get(
                    "inventory.expiry_report.table.column.name",
                    "Product Name",
                ),
                self._translator.get(
                    "inventory.expiry_report.table.column.barcode",
                    "Barcode",
                ),
                self._translator.get(
                    "inventory.expiry_report.table.column.batch",
                    "Batch",
                ),
                self._translator.get(
                    "inventory.expiry_report.table.column.quantity",
                    "Quantity",
                ),
                self._translator.get(
                    "inventory.expiry_report.table.column.expiry",
                    "Expiry Date",
                ),
                self._translator.get(
                    "inventory.expiry_report.table.column.days_left",
                    "Days Left",
                ),
            ]
        )

        self.tblExpiry.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tblExpiry.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tblExpiry.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        if self.tblExpiry.verticalHeader() is not None:
            self.tblExpiry.verticalHeader().setVisible(False)

        header = self.tblExpiry.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.tblExpiry)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, parent=self
        )
        layout.addWidget(button_box)

        button_box.rejected.connect(self.reject)
        self.btnRefresh.clicked.connect(self._load_data)
        self.btnExportPDF.clicked.connect(self._export_pdf)

    def _load_data(self) -> None:
        """Load expiry data from controller."""
        try:
            self._current_days = self.spinDays.value()
            products = self._controller.get_products_near_expiry(
                days_threshold=self._current_days
            )

            self.tblExpiry.setRowCount(0)

            if not products:
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator.get(
                        "inventory.expiry_report.info.no_data",
                        "No products found with this filter.",
                    ),
                )
                return

            for row_idx, product in enumerate(products):
                self.tblExpiry.insertRow(row_idx)

                name_item = QTableWidgetItem(product.get("name", ""))
                barcode_item = QTableWidgetItem(product.get("barcode", ""))
                batch_item = QTableWidgetItem(product.get("batch_number", ""))

                quantity = product.get("quantity", Decimal("0"))
                quantity_item = QTableWidgetItem(f"{float(quantity):,.2f}")
                quantity_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )

                expiry_date = product.get("expiry_date")
                expiry_str = (
                    expiry_date.strftime("%Y-%m-%d")
                    if expiry_date
                    else "-"
                )
                expiry_item = QTableWidgetItem(expiry_str)
                expiry_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                )

                days_left = product.get("days_left", 0)
                days_item = QTableWidgetItem(str(days_left))
                days_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                )

                # Color coding based on days left
                if days_left <= 7:
                    color = QColor(255, 100, 100, 150)  # Red
                elif days_left <= 30:
                    color = QColor(255, 255, 100, 150)  # Yellow
                else:
                    color = QColor(144, 238, 144, 150)  # Light Green

                brush = QBrush(color)
                for item in [
                    name_item,
                    barcode_item,
                    batch_item,
                    quantity_item,
                    expiry_item,
                    days_item,
                ]:
                    item.setBackground(brush)

                self.tblExpiry.setItem(row_idx, 0, name_item)
                self.tblExpiry.setItem(row_idx, 1, barcode_item)
                self.tblExpiry.setItem(row_idx, 2, batch_item)
                self.tblExpiry.setItem(row_idx, 3, quantity_item)
                self.tblExpiry.setItem(row_idx, 4, expiry_item)
                self.tblExpiry.setItem(row_idx, 5, days_item)

        except Exception as exc:
            logger.exception("Error loading expiry report: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )

    def _export_pdf(self) -> None:
        """Export report to PDF."""
        try:
            from PyQt6.QtGui import QTextDocument
            from PyQt6.QtPrintSupport import QPrinter
            from datetime import datetime

            if self.tblExpiry.rowCount() == 0:
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator.get(
                        "inventory.expiry_report.info.no_data",
                        "No data to export.",
                    ),
                )
                return

            filename, _ = QFileDialog.getSaveFileName(
                self,
                self._translator.get(
                    "inventory.expiry_report.button.export_pdf",
                    "Save Expiry Report",
                ),
                f"expiry_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                "PDF Files (*.pdf)",
            )

            if not filename:
                return

            # Build HTML
            rows_html = ""
            for row in range(self.tblExpiry.rowCount()):
                name = self.tblExpiry.item(row, 0).text()
                barcode = self.tblExpiry.item(row, 1).text()
                batch = self.tblExpiry.item(row, 2).text()
                qty = self.tblExpiry.item(row, 3).text()
                expiry = self.tblExpiry.item(row, 4).text()
                days = self.tblExpiry.item(row, 5).text()

                rows_html += f"""
                <tr>
                    <td>{name}</td>
                    <td>{barcode}</td>
                    <td>{batch}</td>
                    <td style="text-align:right;">{qty}</td>
                    <td style="text-align:center;">{expiry}</td>
                    <td style="text-align:center;">{days}</td>
                </tr>
                """

            title = self._translator.get(
                "inventory.expiry_report.pdf.title",
                "Products Near Expiry Report",
            )
            date_text = self._translator.get(
                "inventory.expiry_report.pdf.date",
                "Report Date: {date}",
            ).format(date=datetime.now().strftime("%Y-%m-%d %H:%M"))
            filter_text = self._translator.get(
                "inventory.expiry_report.pdf.filter",
                "Filter: Products under {days} days",
            ).format(days=self._current_days)

            header_name = self._translator.get(
                "inventory.expiry_report.table.column.name",
                "Product Name",
            )
            header_barcode = self._translator.get(
                "inventory.expiry_report.table.column.barcode",
                "Barcode",
            )
            header_batch = self._translator.get(
                "inventory.expiry_report.table.column.batch",
                "Batch",
            )
            header_quantity = self._translator.get(
                "inventory.expiry_report.table.column.quantity",
                "Quantity",
            )
            header_expiry = self._translator.get(
                "inventory.expiry_report.table.column.expiry",
                "Expiry Date",
            )
            header_days_left = self._translator.get(
                "inventory.expiry_report.table.column.days_left",
                "Days Left",
            )

            html = f"""
            <html dir="rtl">
            <head>
                <meta charset="utf-8" />
                <style>
                    body {{
                        font-family: 'Tahoma', sans-serif;
                        direction: rtl;
                    }}
                    h1 {{ text-align: center; font-size: 16pt; }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 10px;
                    }}
                    th, td {{
                        border: 1px solid #333;
                        padding: 6px;
                    }}
                    th {{
                        background-color: #0f172a;
                        color: white;
                    }}
                </style>
            </head>
            <body>
                <h1>{title}</h1>
                <p>{date_text}</p>
                <p>{filter_text}</p>
                <table>
                    <thead>
                        <tr>
                            <th>{header_name}</th>
                            <th>{header_barcode}</th>
                            <th>{header_batch}</th>
                            <th>{header_quantity}</th>
                            <th>{header_expiry}</th>
                            <th>{header_days_left}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </body>
            </html>
            """

            document = QTextDocument()
            document.setHtml(html)

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(filename)

            document.print(printer)

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator.get(
                    "inventory.inventory_report.info.exported",
                    "Report saved successfully.",
                ),
            )

        except Exception as exc:
            logger.exception("Error exporting PDF: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )

class InventoryReportDialog(QDialog):
    """
    Dialog for displaying complete inventory summary with export options.
    """

    def __init__(
        self,
        translator: TranslationManager,
        controller: InventoryController,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._controller = controller
        self._summary_data = None
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        self.setModal(True)
        self.setMinimumSize(900, 600)
        self.setWindowTitle(
            self._translator.get(
                "inventory.inventory_report.dialog.title",
                "Inventory Stock Report",
            )
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header with total value
        header_layout = QHBoxLayout()
        self.lblTotalValue = QLabel(self)
        self.lblTotalValue.setStyleSheet(
            "font-size: 14pt; font-weight: bold; color: #0f172a;"
        )
        header_layout.addWidget(self.lblTotalValue)
        header_layout.addStretch()

        self.btnExportPDF = QPushButton(self)
        self.btnExportPDF.setText(
            self._translator.get(
                "inventory.inventory_report.button.export_pdf",
                "Export PDF",
            )
        )
        header_layout.addWidget(self.btnExportPDF)

        self.btnExportExcel = QPushButton(self)
        self.btnExportExcel.setText(
            self._translator.get(
                "inventory.inventory_report.button.export_excel",
                "Export Excel",
            )
        )
        header_layout.addWidget(self.btnExportExcel)

        layout.addLayout(header_layout)

        # Table
        self.tblInventory = QTableWidget(self)
        self.tblInventory.setColumnCount(7)
        self.tblInventory.setHorizontalHeaderLabels(
            [
                self._translator["inventory.table.column.name"],
                self._translator["inventory.table.column.barcode"],
                self._translator["inventory.table.column.category"],
                self._translator.get("inventory.table.column.unit", "Unit"),
                self._translator["inventory.table.column.total_stock"],
                self._translator.get(
                    "inventory.table.column.avg_buy_price", "Avg Buy Price"
                ),
                self._translator.get("inventory.table.column.value", "Total Value"),
            ]
        )

        self.tblInventory.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tblInventory.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tblInventory.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        if self.tblInventory.verticalHeader() is not None:
            self.tblInventory.verticalHeader().setVisible(False)

        header = self.tblInventory.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(3, 80)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.tblInventory)

        # Close button
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, parent=self
        )
        layout.addWidget(button_box)

        button_box.rejected.connect(self.reject)
        self.btnExportPDF.clicked.connect(self._export_pdf)
        self.btnExportExcel.clicked.connect(self._export_excel)

    def _format_money(self, amount: Decimal) -> str:
        """Format money with thousand separators."""
        try:
            return f"{float(amount):,.0f}"
        except Exception:
            return "0"

    def _load_data(self) -> None:
        """Load inventory summary from controller."""
        try:
            self._summary_data = self._controller.get_inventory_summary()

            total_value = self._summary_data.get("total_value", Decimal("0"))
            self.lblTotalValue.setText(
                self._translator.get(
                    "inventory.inventory_report.label.total_value",
                    "Total Inventory Value: {value} Rials",
                ).format(value=self._format_money(total_value))
            )

            items = self._summary_data.get("items", [])
            self.tblInventory.setRowCount(0)

            for row_idx, item in enumerate(items):
                self.tblInventory.insertRow(row_idx)

                name_item = QTableWidgetItem(item.get("name", ""))
                barcode_item = QTableWidgetItem(item.get("barcode", ""))
                category_item = QTableWidgetItem(item.get("category", ""))
                unit_item = QTableWidgetItem(item.get("unit", "Pcs"))

                quantity = item.get("quantity", Decimal("0"))
                quantity_item = QTableWidgetItem(self._format_money(quantity))
                quantity_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )

                avg_price = item.get("avg_buy_price", Decimal("0"))
                avg_price_item = QTableWidgetItem(self._format_money(avg_price))
                avg_price_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )

                total_val = item.get("total_value", Decimal("0"))
                value_item = QTableWidgetItem(self._format_money(total_val))
                value_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )

                self.tblInventory.setItem(row_idx, 0, name_item)
                self.tblInventory.setItem(row_idx, 1, barcode_item)
                self.tblInventory.setItem(row_idx, 2, category_item)
                self.tblInventory.setItem(row_idx, 3, unit_item)
                self.tblInventory.setItem(row_idx, 4, quantity_item)
                self.tblInventory.setItem(row_idx, 5, avg_price_item)
                self.tblInventory.setItem(row_idx, 6, value_item)

        except Exception as exc:
            logger.exception("Error loading inventory summary: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )

    def _export_pdf(self) -> None:
        """Export inventory report to PDF."""
        try:
            from PyQt6.QtGui import QTextDocument
            from PyQt6.QtPrintSupport import QPrinter
            from datetime import datetime

            if not self._summary_data or not self._summary_data.get("items"):
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator.get(
                        "reports.export.no_data",
                        "No data to export.",
                    ),
                )
                return

            filename, _ = QFileDialog.getSaveFileName(
                self,
                self._translator.get(
                    "inventory.inventory_report.button.export_pdf",
                    "Save Inventory Report",
                ),
                f"inventory_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                "PDF Files (*.pdf)",
            )

            if not filename:
                return

            # Build HTML
            rows_html = ""
            for item in self._summary_data["items"]:
                name = item.get("name", "")
                barcode = item.get("barcode", "")
                category = item.get("category", "")
                unit = item.get("unit", "Pcs")
                qty = self._format_money(item.get("quantity", Decimal("0")))
                avg_price = self._format_money(item.get("avg_buy_price", Decimal("0")))
                value = self._format_money(item.get("total_value", Decimal("0")))

                rows_html += f"""
                <tr>
                    <td>{name}</td>
                    <td>{barcode}</td>
                    <td>{category}</td>
                    <td style="text-align:center;">{unit}</td>
                    <td style="text-align:right;">{qty}</td>
                    <td style="text-align:right;">{avg_price}</td>
                    <td style="text-align:right;">{value}</td>
                </tr>
                """

            total_value = self._format_money(
                self._summary_data.get("total_value", Decimal("0"))
            )
            total_items = self._summary_data.get("total_items", 0)

            title = self._translator.get(
                "inventory.inventory_report.pdf.title",
                "Inventory Stock Report",
            )
            date_text = self._translator.get(
                "inventory.inventory_report.pdf.date",
                "Report Date: {date}",
            ).format(date=datetime.now().strftime("%Y-%m-%d %H:%M"))
            total_items_text = self._translator.get(
                "inventory.inventory_report.pdf.total_items",
                "Total Items: {count}",
            ).format(count=total_items)
            total_value_text = self._translator.get(
                "inventory.inventory_report.pdf.total_value",
                "Total Inventory Value: {value} Rials",
            ).format(value=total_value)

            header_name = self._translator.get(
                "inventory.inventory_report.csv.header.name",
                "Product Name",
            )
            header_barcode = self._translator.get(
                "inventory.inventory_report.csv.header.barcode",
                "Barcode",
            )
            header_category = self._translator.get(
                "inventory.inventory_report.csv.header.category",
                "Category",
            )
            header_unit = self._translator.get(
                "inventory.inventory_report.csv.header.unit",
                "Unit",
            )
            header_quantity = self._translator.get(
                "inventory.inventory_report.csv.header.quantity",
                "Quantity",
            )
            header_avg_price = self._translator.get(
                "inventory.inventory_report.csv.header.avg_price",
                "Avg Buy Price",
            )
            header_value = self._translator.get(
                "inventory.inventory_report.csv.header.value",
                "Total Value",
            )
            total_label = self._translator.get(
                "inventory.inventory_report.pdf.table.total_label",
                "Total",
            )

            html = f"""
            <html dir="rtl">
            <head>
                <meta charset="utf-8" />
                <style>
                    body {{ font-family: 'Tahoma', sans-serif; direction: rtl; }}
                    h1 {{ text-align: center; font-size: 16pt; margin-bottom: 5px; }}
                    .summary {{ text-align: center; margin-bottom: 15px; }}
                    table {{ width: 100%; border-collapse: collapse; font-size: 9pt; }}
                    th, td {{ border: 1px solid #333; padding: 4px; }}
                    th {{ background-color: #0f172a; color: white; }}
                    .total-row {{ font-weight: bold; background-color: #f3f4f6; }}
                </style>
            </head>
            <body>
                <h1>{title}</h1>
                <div class="summary">
                    <p>{date_text}</p>
                    <p>{total_items_text}</p>
                    <p style="font-size: 12pt; font-weight: bold;">{total_value_text}</p>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>{header_name}</th>
                            <th>{header_barcode}</th>
                            <th>{header_category}</th>
                            <th>{header_unit}</th>
                            <th>{header_quantity}</th>
                            <th>{header_avg_price}</th>
                            <th>{header_value}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                        <tr class="total-row">
                            <td colspan="6" style="text-align:left;">{total_label}</td>
                            <td style="text-align:right;">{total_value}</td>
                        </tr>
                    </tbody>
                </table>
            </body>
            </html>
            """

            document = QTextDocument()
            document.setHtml(html)

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(filename)

            document.print(printer)

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator.get(
                    "inventory.inventory_report.info.exported",
                    "Report saved successfully.",
                ),
            )

        except Exception as exc:
            logger.exception("Error exporting inventory PDF: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )

    def _export_excel(self) -> None:
        """Export inventory report to CSV (Excel-compatible)."""
        try:
            from datetime import datetime
            import csv

            if not self._summary_data or not self._summary_data.get("items"):
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator.get(
                        "reports.export.no_data",
                        "No data to export.",
                    ),
                )
                return

            filename, _ = QFileDialog.getSaveFileName(
                self,
                self._translator.get(
                    "inventory.inventory_report.button.export_excel",
                    "Save Inventory Report",
                ),
                f"inventory_report_{datetime.now().strftime('%Y%m%d')}.csv",
                "CSV Files (*.csv)",
            )

            if not filename:
                return

            with open(filename, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)

                # Headers
                writer.writerow(
                    [
                        self._translator.get(
                            "inventory.inventory_report.csv.header.name",
                            "Product Name",
                        ),
                        self._translator.get(
                            "inventory.inventory_report.csv.header.barcode",
                            "Barcode",
                        ),
                        self._translator.get(
                            "inventory.inventory_report.csv.header.category",
                            "Category",
                        ),
                        self._translator.get(
                            "inventory.inventory_report.csv.header.unit",
                            "Unit",
                        ),
                        self._translator.get(
                            "inventory.inventory_report.csv.header.quantity",
                            "Quantity",
                        ),
                        self._translator.get(
                            "inventory.inventory_report.csv.header.avg_price",
                            "Avg Buy Price",
                        ),
                        self._translator.get(
                            "inventory.inventory_report.csv.header.value",
                            "Total Value",
                        ),
                    ]
                )

                # Data rows
                for item in self._summary_data["items"]:
                    writer.writerow(
                        [
                            item.get("name", ""),
                            item.get("barcode", ""),
                            item.get("category", ""),
                            item.get("unit", "Pcs"),
                            float(item.get("quantity", Decimal("0"))),
                            float(item.get("avg_buy_price", Decimal("0"))),
                            float(item.get("total_value", Decimal("0"))),
                        ]
                    )

                # Total row
                writer.writerow([])
                writer.writerow(
                    [
                        "",
                        "",
                        "",
                        "",
                        "",
                        self._translator.get(
                            "inventory.inventory_report.csv.total_label",
                            "Total:",
                        ),
                        float(self._summary_data.get("total_value", Decimal("0"))),
                    ]
                )

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator.get(
                    "inventory.inventory_report.info.exported",
                    "Report saved successfully.",
                ),
            )

        except Exception as exc:
            logger.exception("Error exporting inventory CSV: %s", exc)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(exc),
            )