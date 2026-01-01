
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from PyQt6 import uic
from PyQt6.QtCore import Qt, QPoint, QMarginsF, pyqtSignal
from PyQt6.QtGui import (
    QDoubleValidator,
    QKeySequence,
    QShortcut,
    QTextDocument,
    QPageLayout,
)
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import LOYALTY_EARN_RATE, LOYALTY_EARN_THRESHOLD, LOYALTY_POINT_VALUE
from app.controllers.sales_controller import SalesController
from app.core.translation_manager import TranslationManager
from app.models.models import UserAccount
from app.views.components.scanner_dialog import ScannerDialog
from app.views.components.return_dialog import ReturnDialog
from app.views.components.close_shift_dialog import CloseShiftDialog
from app.views.customers_view import CustomersDialog

logger = logging.getLogger(__name__)


class StartShiftDialog(QDialog):
    """
    Dialog for starting a new shift with an initial cash float.

    The dialog is fully localized using TranslationManager and performs
    basic validation on the entered cash amount.
    """

    def __init__(
            self,
            translation_manager: TranslationManager,
            parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translation_manager
        self._cash_float = Decimal("0")
        try:
            self._build_ui()
        except Exception as e:
            logger.error("Error initializing StartShiftDialog: %s", e, exc_info=True)

    def _build_ui(self) -> None:
        try:
            self.setWindowTitle(self._translator["shift.start_title"])

            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            description = QLabel(self._translator["shift.start_message"], self)
            description.setWordWrap(True)
            layout.addWidget(description)

            form_layout = QFormLayout()
            form_layout.setContentsMargins(0, 0, 0, 0)
            form_layout.setSpacing(8)

            self.txt_cash_float = QLineEdit(self)
            self.txt_cash_float.setText("0")
            # Apply numeric validator to prevent non-numeric input
            validator = QDoubleValidator(self)
            validator.setBottom(0.0)
            self.txt_cash_float.setValidator(validator)
            try:
                self.txt_cash_float.setPlaceholderText(
                    self._translator["shift.cash_float_placeholder"]
                )
            except Exception:
                # If translation key is missing, ignore placeholder configuration.
                pass

            form_layout.addRow(
                self._translator["shift.cash_float_label"],
                self.txt_cash_float,
            )
            layout.addLayout(form_layout)

            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel,
                parent=self,
                )
            layout.addWidget(button_box)

            button_box.accepted.connect(self._on_accept)
            button_box.rejected.connect(self.reject)
        except Exception as e:
            logger.error("Error building StartShiftDialog UI: %s", e, exc_info=True)

    def _on_accept(self) -> None:
        try:
            raw = (self.txt_cash_float.text() or "").strip()
            if not raw:
                raw = "0"
            try:
                amount = Decimal(raw)
            except Exception:
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator["shift.error.invalid_amount"],
                )
                return

            if amount < 0:
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator["shift.error.negative_amount"],
                )
                return

            self._cash_float = amount.quantize(Decimal("0.01"))
            self.accept()
        except Exception as e:
            logger.error(
                "Error validating cash float in StartShiftDialog: %s",
                e,
                exc_info=True,
            )
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                self._translator["shift.error.invalid_amount"],
            )

    def cash_float(self) -> Decimal:
        return self._cash_float


class SalesView(QWidget):
    """
    Point-of-Sale (POS) view for the Sales module.

    Loads its layout from app/views/ui/sales_view.ui and wires the UI
    elements to SalesController, handling barcode scanning, cart management,
    and checkout.
    """

    # Emitted after a shift has been successfully closed, with the summary
    # dictionary returned by SalesController.close_shift.
    shift_closed = pyqtSignal(dict)

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
        self._selected_customer_id: Optional[int] = None
        self._selected_customer_name: str = ""
        self._return_mode: bool = False
        self._loyalty_points_balance: int = 0
        self._loyalty_points_to_redeem: int = 0
        self._loyalty_discount_value: Decimal = Decimal("0")
        self._current_subtotal: Decimal = Decimal("0")
        self._current_manual_discount: Decimal = Decimal("0")
        self._current_total_amount: Decimal = Decimal("0")

        uic.loadUi("app/views/ui/sales_view.ui", self)

        self._inject_scan_barcode_button()
        self._inject_customer_controls()
        self._inject_loyalty_controls()
        self._inject_return_mode_toggle()
        self._inject_returns_button()
        self._inject_close_shift_button()
        self._inject_clear_cart_button()
        self._inject_discount_control()
        self._inject_parking_buttons()
        self._updating_cart_items = False

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
    def _inject_scan_barcode_button(self) -> None:
        try:
            top_layout = getattr(self, "horizontalLayout_top", None)
            if top_layout is None:
                logger.warning(
                    "SalesView top layout not found; cannot inject Scan Barcode button."
                )
                return

            self.btnScanBarcode = getattr(self, "btnScanBarcode", None)
            if self.btnScanBarcode is None:
                self.btnScanBarcode = QPushButton(self)
                self.btnScanBarcode.setObjectName("btnScanBarcode")
                self.btnScanBarcode.setText(
                    self._translator.get(
                        "sales.button.scan_barcode",
                        "📷 Scan Barcode",
                    )
                )
                top_layout.addWidget(self.btnScanBarcode)
        except Exception as e:
            logger.error("Error in _inject_scan_barcode_button: %s", e, exc_info=True)

    def _inject_customer_controls(self) -> None:
        try:
            # These widgets are expected in the .ui, fall back to creating them if missing.
            self.lblCustomer = getattr(self, "lblCustomer", None)
            self.btnSelectCustomer = getattr(self, "btnSelectCustomer", None)

            if self.lblCustomer is None:
                self.lblCustomer = QLabel(self)
                self.lblCustomer.setObjectName("lblSelectedCustomer")
                self.lblCustomer.setText("مشتری: -")

            if self.btnSelectCustomer is None:
                self.btnSelectCustomer = QPushButton(self)
                self.btnSelectCustomer.setObjectName("btnSelectCustomer")
                self.btnSelectCustomer.setText("انتخاب مشتری")

            top_layout = getattr(self, "horizontalLayout_top", None)
            if top_layout is not None:
                top_layout.addWidget(self.lblCustomer)
                top_layout.addWidget(self.btnSelectCustomer)
            else:
                # If no dedicated layout, leave widgets unmanaged; they can still be used.
                self.lblCustomer.setParent(self)
                self.btnSelectCustomer.setParent(self)
        except Exception as e:
            logger.error("Error in _inject_customer_controls: %s", e, exc_info=True)

    def _inject_loyalty_controls(self) -> None:
        """
        Inject loyalty points info label and redemption spinbox near the customer controls.
        """
        try:
            top_layout = getattr(self, "horizontalLayout_top", None)
            if top_layout is None:
                logger.warning(
                    "SalesView top layout not found; cannot inject loyalty controls."
                )
                return

            self.lblLoyaltyInfo = getattr(self, "lblLoyaltyInfo", None)
            self.spinRedeemPoints = getattr(self, "spinRedeemPoints", None)

            if self.lblLoyaltyInfo is None:
                self.lblLoyaltyInfo = QLabel(self)
                self.lblLoyaltyInfo.setObjectName("lblLoyaltyInfo")

            if self.spinRedeemPoints is None:
                self.spinRedeemPoints = QSpinBox(self)
                self.spinRedeemPoints.setObjectName("spinRedeemPoints")
                self.spinRedeemPoints.setMinimum(0)
                self.spinRedeemPoints.setMaximum(0)
                self.spinRedeemPoints.setValue(0)

            top_layout.addWidget(self.lblLoyaltyInfo)
            top_layout.addWidget(self.spinRedeemPoints)
        except Exception as e:
            logger.error("Error in _inject_loyalty_controls: %s", e, exc_info=True)

    def _inject_return_mode_toggle(self) -> None:
        try:
            self.chkReturnMode = getattr(self, "chkReturnMode", None)
            if self.chkReturnMode is None:
                self.chkReturnMode = QCheckBox(self)
                self.chkReturnMode.setObjectName("chkReturnMode")
                self.chkReturnMode.setText("حالت مرجوعی")

            top_layout = getattr(self, "horizontalLayout_top", None)
            if top_layout is not None:
                top_layout.addWidget(self.chkReturnMode)
            else:
                self.chkReturnMode.setParent(self)
        except Exception as e:
            logger.error("Error in _inject_return_mode_toggle: %s", e, exc_info=True)

    def _inject_returns_button(self) -> None:
        """
        Inject a dedicated 'Returns / Refund' button that opens the ReturnDialog.
        """
        try:
            top_layout = getattr(self, "horizontalLayout_top", None)
            if top_layout is None:
                logger.warning(
                    "SalesView top layout not found; cannot inject Returns button."
                )
                return

            self.btnReturns = getattr(self, "btnReturns", None)
            if self.btnReturns is None:
                self.btnReturns = QPushButton(self)
                self.btnReturns.setObjectName("btnReturns")
                self.btnReturns.setText("Returns / Refund")

            top_layout.addWidget(self.btnReturns)
        except Exception as e:
            logger.error("Error in _inject_returns_button: %s", e, exc_info=True)

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

    def _inject_clear_cart_button(self) -> None:
        try:
            layout = getattr(self, "horizontalLayout_bottom", None)
            if layout is None:
                logger.warning(
                    "SalesView bottom layout not found; cannot inject Clear Cart button."
                )
                return

            self.btnClearCart = QPushButton(self)
            self.btnClearCart.setObjectName("btnClearCart")
            self.btnClearCart.setText("Clear Cart")

            insert_index = max(0, layout.count() - 1)
            layout.insertWidget(insert_index, self.btnClearCart)
            self.btnClearCart.clicked.connect(self._on_clear_cart_clicked)

            logger.info("Clear Cart button injected into SalesView layout.")
        except Exception as e:
            logger.error("Error in _inject_clear_cart_button: %s", e, exc_info=True)

    def _inject_discount_control(self) -> None:
        try:
            bottom_layout = getattr(self, "horizontalLayout_bottom", None)
            if bottom_layout is None:
                logger.warning(
                    "SalesView bottom layout not found; cannot inject discount control."
                )
                return

            self.lblDiscount = getattr(self, "lblDiscount", None)
            self.spinDiscount = getattr(self, "spinDiscount", None)

            if self.lblDiscount is None:
                self.lblDiscount = QLabel(self)
                self.lblDiscount.setObjectName("lblDiscount")
                self.lblDiscount.setText("تخفیف:")

            if self.spinDiscount is None:
                self.spinDiscount = QDoubleSpinBox(self)
                self.spinDiscount.setObjectName("spinDiscount")
                self.spinDiscount.setRange(0.0, 100_000_000.0)
                self.spinDiscount.setDecimals(2)
                self.spinDiscount.setSingleStep(1000.0)
                self.spinDiscount.setValue(0.0)

            # Insert before Clear Cart / Close Shift / Checkout buttons if possible
            insert_index = max(0, bottom_layout.count() - 3)
            bottom_layout.insertWidget(insert_index, self.lblDiscount)
            bottom_layout.insertWidget(insert_index + 1, self.spinDiscount)

            logger.info("Discount control injected into SalesView layout.")
        except Exception as e:
            logger.error("Error in _inject_discount_control: %s", e, exc_info=True)

    def _inject_parking_buttons(self) -> None:
        try:
            layout = getattr(self, "horizontalLayout_bottom", None)
            if layout is None:
                logger.warning(
                    "SalesView bottom layout not found; cannot inject parking buttons."
                )
                return

            self.btnHoldOrder = QPushButton(self)
            self.btnHoldOrder.setObjectName("btnHoldOrder")

            self.btnRecallOrder = QPushButton(self)
            self.btnRecallOrder.setObjectName("btnRecallOrder")

            insert_index = max(0, layout.count() - 1)
            layout.insertWidget(insert_index, self.btnRecallOrder)
            layout.insertWidget(insert_index, self.btnHoldOrder)

            logger.info("Hold/Recall order buttons injected into SalesView layout.")
        except Exception as e:
            logger.error("Error in _inject_parking_buttons: %s", e, exc_info=True)

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
                self.btnCloseShift.setText(
                    self._translator["shift.close_button"]
                )
            if hasattr(self, "btnClearCart"):
                self.btnClearCart.setText(
                    self._translator.get("sales.button.clear", "Clear Cart")
                )
            if hasattr(self, "btnSelectCustomer"):
                self.btnSelectCustomer.setText(
                    self._translator.get(
                        "sales.button.select_customer",
                        "Select Customer",
                    )
                )
            if hasattr(self, "btnScanBarcode"):
                self.btnScanBarcode.setText(
                    self._translator.get(
                        "sales.button.scan_barcode",
                        "📷 Scan Barcode",
                    )
                )
            if hasattr(self, "btnHoldOrder"):
                self.btnHoldOrder.setText(
                    self._translator.get("sales.button.hold", "Hold Order")
                )
            if hasattr(self, "btnRecallOrder"):
                self.btnRecallOrder.setText(
                    self._translator.get("sales.button.recall", "Recall Order")
                )
            if hasattr(self, "chkReturnMode"):
                self.chkReturnMode.setText(
                    self._translator.get("sales.mode.return", "Return Mode")
                )
            if hasattr(self, "btnReturns"):
                self.btnReturns.setText(
                    self._translator.get(
                        "sales.button.returns",
                        "Returns / Refund",
                    )
                )
            if hasattr(self, "lblDiscount"):
                self.lblDiscount.setText(
                    self._translator.get("sales.label.discount", "Discount") + ":"
                )

            self._update_customer_label()
            self._update_loyalty_label()
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
            self._translator.get("sales.table.column.delete", "X"),
        ]
        self.tblCart.setColumnCount(len(headers))
        self.tblCart.setHorizontalHeaderLabels(headers)

        self.tblCart.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tblCart.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        # Allow editing where item flags permit (quantity column)
        self.tblCart.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
        )

        # Enable context menu on cart table
        self.tblCart.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.tblCart.customContextMenuRequested.connect(
            self._on_cart_context_menu
        )

        if self.tblCart.verticalHeader() is not None:
            self.tblCart.verticalHeader().setVisible(False)
            # Increase default row height so embedded widgets (spinboxes, buttons)
            # are fully visible and not clipped.
            self.tblCart.verticalHeader().setDefaultSectionSize(45)

        header = self.tblCart.horizontalHeader()
        if header is not None:
            from PyQt6.QtWidgets import QHeaderView

            header.setStretchLastSection(False)
            # Name column stretches
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            # Quantity column fixed
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(1, 70)
            # Price and Row Total auto
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            # Delete column fixed and narrow
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(4, 40)

    def _setup_shortcuts(self) -> None:
        # Allow deleting the selected cart row with the Delete key
        self._delete_shortcut = QShortcut(QKeySequence("Delete"), self.tblCart)
        self._delete_shortcut.activated.connect(self._remove_selected_row)

    def _connect_signals(self) -> None:
        self.txtBarcode.returnPressed.connect(self._on_barcode_entered)
        self.btnSearch.clicked.connect(self._on_barcode_entered)
        self.btnCheckout.clicked.connect(self._on_checkout_clicked)
        if hasattr(self, "btnSelectCustomer"):
            self.btnSelectCustomer.clicked.connect(self._on_select_customer_clicked)
        if hasattr(self, "btnScanBarcode"):
            self.btnScanBarcode.clicked.connect(self._on_scan_barcode_clicked)
        if hasattr(self, "btnClearCart"):
            self.btnClearCart.clicked.connect(self._on_clear_cart_clicked)
        if hasattr(self, "btnHoldOrder"):
            self.btnHoldOrder.clicked.connect(self._on_hold_order_clicked)
        if hasattr(self, "btnRecallOrder"):
            self.btnRecallOrder.clicked.connect(self._on_recall_order_clicked)
        if hasattr(self, "chkReturnMode"):
            self.chkReturnMode.toggled.connect(self._on_return_mode_toggled)
        if hasattr(self, "btnReturns"):
            self.btnReturns.clicked.connect(self._on_returns_clicked)
        if hasattr(self, "spinDiscount") and self.spinDiscount is not None:
            self.spinDiscount.valueChanged.connect(lambda _: self._recalculate_total())
        if hasattr(self, "spinRedeemPoints") and self.spinRedeemPoints is not None:
            self.spinRedeemPoints.valueChanged.connect(self._on_redeem_points_changed)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _format_money(self, amount: Decimal) -> str:
        quantized = amount.quantize(Decimal("0.01"))
        sign = "-" if amount < 0 else ""
        return f"{sign}{abs(float(quantized)):.2f}"

    def _update_customer_label(self) -> None:
        try:
            if not hasattr(self, "lblCustomer"):
                return
            label_prefix = self._translator.get(
                "sales.customer.label", "Customer: "
            )
            if self._selected_customer_name:
                self.lblCustomer.setText(
                    f"{label_prefix}{self._selected_customer_name}"
                )
            else:
                self.lblCustomer.setText(f"{label_prefix}-")
        except Exception as e:
            logger.error("Error in _update_customer_label: %s", e, exc_info=True)

    def _update_loyalty_label(self) -> None:
        try:
            if not hasattr(self, "lblLoyaltyInfo"):
                return

            points = max(int(self._loyalty_points_balance or 0), 0)
            try:
                value_dec = Decimal(points) * Decimal(str(LOYALTY_POINT_VALUE))
            except Exception:
                value_dec = Decimal("0")

            template = self._translator.get(
                "sales.loyalty.label",
                "Loyalty Points: {points} (Value: {value})",
            )
            self.lblLoyaltyInfo.setText(
                template.format(
                    points=points,
                    value=self._format_money(value_dec),
                )
            )
        except Exception as e:
            logger.error("Error in _update_loyalty_label: %s", e, exc_info=True)

    def _on_select_customer_clicked(self) -> None:
        try:
            result = CustomersDialog.select_customer(
                translator=self._translator,
                parent=self,
            )
            if result is None:
                return
            cust_id, name = result
            self._selected_customer_id = cust_id
            self._selected_customer_name = name
            self._update_customer_label()
            self._refresh_loyalty_info()
        except Exception as e:
            logger.error("Error in _on_select_customer_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _on_scan_barcode_clicked(self) -> None:
        try:
            dialog = ScannerDialog(translator=self._translator, parent=self)
            dialog.barcode_detected.connect(self._on_scanner_barcode_detected)
            dialog.exec()
        except Exception as e:
            logger.error("Error in _on_scan_barcode_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _on_returns_clicked(self) -> None:
        try:
            dialog = ReturnDialog(
                translation_manager=self._translator,
                controller=self._controller,
                parent=self,
            )
            dialog.exec()
        except Exception as e:
            logger.error("Error in _on_returns_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _on_scanner_barcode_detected(self, code: str) -> None:
        try:
            if not code:
                return
            self.txtBarcode.setText(code)
            self._on_barcode_entered()
        except Exception as e:
            logger.error(
                "Error in _on_scanner_barcode_detected: %s", e, exc_info=True
            )

    def _on_clear_cart_clicked(self) -> None:
        try:
            self._clear_cart()
        except Exception as e:
            logger.error("Error in _on_clear_cart_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _on_return_mode_toggled(self, checked: bool) -> None:
        try:
            self._return_mode = checked
            # Highlight cart border in return mode
            if checked:
                self.tblCart.setStyleSheet(
                    "QTableWidget { border: 2px solid #dc2626; }"
                )
            else:
                self.tblCart.setStyleSheet("")

            # Disable or enable discount in return mode
            if hasattr(self, "spinDiscount") and self.spinDiscount is not None:
                self.spinDiscount.blockSignals(True)
                if checked:
                    # Disable discounts for refunds to avoid complexity
                    self.spinDiscount.setValue(0.0)
                    self.spinDiscount.setEnabled(False)
                else:
                    self.spinDiscount.setEnabled(True)
                self.spinDiscount.blockSignals(False)

            # Disable loyalty redemption in return mode
            if hasattr(self, "spinRedeemPoints") and self.spinRedeemPoints is not None:
                self.spinRedeemPoints.blockSignals(True)
                self.spinRedeemPoints.setValue(0)
                self.spinRedeemPoints.setEnabled(
                    not checked and self._selected_customer_id is not None
                )
                self.spinRedeemPoints.blockSignals(False)
            self._loyalty_points_to_redeem = 0
            self._loyalty_discount_value = Decimal("0")

            # Update prefixes and row totals
            for row in range(self.tblCart.rowCount()):
                spin = self._get_quantity_spinbox(row)
                if spin is None:
                    continue
                spin.blockSignals(True)
                spin.setPrefix("-" if checked else "")
                spin.blockSignals(False)
                self._on_quantity_changed_for_spin(spin, spin.value())

            # Recalculate after mode change
            self._recalculate_total()
        except Exception as e:
            logger.error("Error in _on_return_mode_toggled: %s", e, exc_info=True)

    def _on_redeem_points_changed(self, value: int) -> None:
        try:
            _ = value
            self._recalculate_total()
        except Exception as e:
            logger.error("Error in _on_redeem_points_changed: %s", e, exc_info=True)

    def _on_hold_order_clicked(self) -> None:
        try:
            cart_items = self._collect_cart_items()
            if not cart_items:
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator["sales.info.cart_empty"],
                )
                return

            park_id = self._controller.park_order(
                cart_items=cart_items,
                cust_id=self._selected_customer_id,
            )
            logger.info("Order parked with ParkID=%s", park_id)
            self._clear_cart()
            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator["sales.info.order_held"],
            )
        except Exception as e:
            logger.error("Error in _on_hold_order_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _refresh_loyalty_info(self) -> None:
        """
        Refresh loyalty balance and UI state whenever the selected customer changes.
        """
        try:
            if not hasattr(self, "lblLoyaltyInfo"):
                return

            if self._selected_customer_id is None:
                self._loyalty_points_balance = 0
                self._loyalty_points_to_redeem = 0
                self._loyalty_discount_value = Decimal("0")
                if hasattr(self, "spinRedeemPoints") and self.spinRedeemPoints is not None:
                    self.spinRedeemPoints.blockSignals(True)
                    self.spinRedeemPoints.setMaximum(0)
                    self.spinRedeemPoints.setValue(0)
                    self.spinRedeemPoints.setEnabled(False)
                    self.spinRedeemPoints.blockSignals(False)
                self._update_loyalty_label()
                self._recalculate_total()
                return

            points = 0
            try:
                points = self._controller.get_customer_loyalty_points(self._selected_customer_id)
            except Exception as exc:
                logger.error(
                    "Error fetching loyalty points for CustID=%s: %s",
                    self._selected_customer_id,
                    exc,
                    exc_info=True,
                )
                points = 0

            self._loyalty_points_balance = max(int(points or 0), 0)

            if hasattr(self, "spinRedeemPoints") and self.spinRedeemPoints is not None:
                self.spinRedeemPoints.blockSignals(True)
                self.spinRedeemPoints.setMaximum(self._loyalty_points_balance)
                if self.spinRedeemPoints.value() > self._loyalty_points_balance:
                    self.spinRedeemPoints.setValue(self._loyalty_points_balance)
                self.spinRedeemPoints.setEnabled(True)
                self.spinRedeemPoints.blockSignals(False)

            self._update_loyalty_label()
            self._recalculate_total()
        except Exception as e:
            logger.error("Error in _refresh_loyalty_info: %s", e, exc_info=True)

    def _on_recall_order_clicked(self) -> None:
        try:
            orders = self._controller.get_parked_orders()
            if not orders:
                QMessageBox.information(
                    self,
                    self._translator["dialog.info_title"],
                    self._translator["sales.info.no_held_orders"],
                )
                return

            dialog = QDialog(self)
            dialog.setWindowTitle(
                self._translator.get(
                    "sales.dialog.parked_orders.title",
                    "Parked Orders",
                )
            )
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            table = QTableWidget(dialog)
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(
                [
                    self._translator.get(
                        "sales.dialog.parked_orders.column.id", "ID"
                    ),
                    self._translator.get(
                        "sales.dialog.parked_orders.column.customer",
                        "Customer",
                    ),
                    self._translator.get(
                        "sales.dialog.parked_orders.column.time", "Time"
                    ),
                    self._translator.get(
                        "sales.dialog.parked_orders.column.total", "Total"
                    ),
                ]
            )
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(
                QAbstractItemView.SelectionMode.SingleSelection
            )
            if table.verticalHeader() is not None:
                table.verticalHeader().setVisible(False)

            table.setRowCount(0)
            for row_idx, order in enumerate(orders):
                table.insertRow(row_idx)
                id_item = QTableWidgetItem(str(order["park_id"]))
                id_item.setData(Qt.ItemDataRole.UserRole, int(order["park_id"]))
                cust_item = QTableWidgetItem(order.get("customer_name") or "-")
                created = order.get("created_at")
                created_text = (
                    created.strftime("%Y-%m-%d %H:%M")
                    if hasattr(created, "strftime")
                    else ""
                )
                created_item = QTableWidgetItem(created_text)
                total_item = QTableWidgetItem(self._format_money(order.get("total", Decimal("0"))))
                total_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )

                table.setItem(row_idx, 0, id_item)
                table.setItem(row_idx, 1, cust_item)
                table.setItem(row_idx, 2, created_item)
                table.setItem(row_idx, 3, total_item)

            layout.addWidget(table)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel,
                parent=dialog,
                )
            layout.addWidget(buttons)

            def _on_accept() -> None:
                if table.currentRow() < 0:
                    QMessageBox.information(
                        dialog,
                        self._translator["dialog.info_title"],
                        self._translator["sales.info.select_order"],
                    )
                    return
                dialog.accept()

            buttons.accepted.connect(_on_accept)
            buttons.rejected.connect(dialog.reject)
            table.doubleClicked.connect(lambda *_: _on_accept())

            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            row = table.currentRow()
            id_item = table.item(row, 0)
            if id_item is None:
                return
            park_id = id_item.data(Qt.ItemDataRole.UserRole) or id_item.text()
            park_id_int = int(park_id)

            restored = self._controller.restore_order(park_id_int)
            items = restored.get("items") or []
            cust_id = restored.get("customer_id")
            cust_name = restored.get("customer_name") or ""

            self._selected_customer_id = cust_id
            self._selected_customer_name = cust_name
            self._update_customer_label()

            self._load_cart_from_items(items)
        except Exception as e:
            logger.error("Error in _on_recall_order_clicked: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _reset_total(self) -> None:
        self._current_subtotal = Decimal("0")
        self._current_manual_discount = Decimal("0")
        self._loyalty_points_to_redeem = 0
        self._loyalty_discount_value = Decimal("0")
        self._current_total_amount = Decimal("0")

        total_text = self._translator["sales.total_prefix"].format(
            amount=self._format_money(Decimal("0"))
        )
        self.lblTotalAmount.setText(total_text)

        # Reset manual discount control
        if hasattr(self, "spinDiscount") and self.spinDiscount is not None:
            try:
                self.spinDiscount.blockSignals(True)
                self.spinDiscount.setValue(0.0)
                self.spinDiscount.setEnabled(not self._return_mode)
            finally:
                self.spinDiscount.blockSignals(False)

        # Reset loyalty redemption control
        if hasattr(self, "spinRedeemPoints") and self.spinRedeemPoints is not None:
            try:
                self.spinRedeemPoints.blockSignals(True)
                self.spinRedeemPoints.setValue(0)
                self.spinRedeemPoints.setEnabled(
                    self._selected_customer_id is not None and not self._return_mode
                )
            finally:
                self.spinRedeemPoints.blockSignals(False)


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
            spin = self._get_quantity_spinbox(existing_row)
            if spin is None:
                return
            new_qty = spin.value() + 1
            spin.setValue(new_qty)
            return

        row = self.tblCart.rowCount()
        self.tblCart.insertRow(row)

        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.ItemDataRole.UserRole, prod_id)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

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
        self.tblCart.setItem(row, 2, price_item)
        self.tblCart.setItem(row, 3, row_total_item)

        # Quantity spinbox inside centered container
        spin = QSpinBox(self.tblCart)
        spin.setMinimum(1)
        spin.setMaximum(1000000)
        spin.setValue(1)
        spin.setFixedSize(60, 35)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setPrefix("-" if self._return_mode else "")
        spin.valueChanged.connect(
            lambda value, s=spin: self._on_quantity_changed_for_spin(s, value)
        )

        qty_container = QWidget(self.tblCart)
        qty_layout = QHBoxLayout(qty_container)
        qty_layout.setContentsMargins(0, 0, 0, 0)
        qty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qty_layout.addWidget(spin)
        self.tblCart.setCellWidget(row, 1, qty_container)

        # Delete button inside centered container
        btn_delete = QPushButton("X", self.tblCart)
        btn_delete.setFixedSize(28, 28)
        btn_delete.setStyleSheet(
            "QPushButton { background-color: #dc2626; color: #ffffff; border: none; border-radius: 4px; }"
            "QPushButton:hover { background-color: #b91c1c; }"
        )
        btn_delete.clicked.connect(
            lambda _, b=btn_delete: self._delete_row_for_button(b)
        )

        del_container = QWidget(self.tblCart)
        del_layout = QHBoxLayout(del_container)
        del_layout.setContentsMargins(0, 0, 0, 0)
        del_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        del_layout.addWidget(btn_delete)
        self.tblCart.setCellWidget(row, 4, del_container)

    def _remove_selected_row(self) -> None:
        try:
            logger.info("Delete shortcut activated in SalesView.")
            row = self.tblCart.currentRow()
            if row < 0:
                return
            self._delete_row(row)
        except Exception as e:
            logger.error("Error in _remove_selected_row: %s", e, exc_info=True)
            QMessageBox.critical(self, "Error", str(e))

    def _get_quantity_spinbox(self, row: int) -> Optional[QSpinBox]:
        container = self.tblCart.cellWidget(row, 1)
        if container is None:
            return None
        spin = container.findChild(QSpinBox)
        return spin

    def _find_row_for_inner_widget(self, widget: QWidget) -> int:
        for row in range(self.tblCart.rowCount()):
            for col in range(self.tblCart.columnCount()):
                cell = self.tblCart.cellWidget(row, col)
                if cell is None:
                    continue
                if cell is widget or widget in cell.findChildren(QWidget):
                    return row
        return -1

    def _delete_row_for_button(self, button: QPushButton) -> None:
        row = self._find_row_for_inner_widget(button)
        if row >= 0:
            self._delete_row(row)

    def _delete_row(self, row: int) -> None:
        if row < 0 or row >= self.tblCart.rowCount():
            return
        self.tblCart.removeRow(row)
        self._recalculate_total()

    def _on_quantity_changed_for_spin(self, spin: QSpinBox, value: int) -> None:
        try:
            if self._updating_cart_items:
                return
            row = self._find_row_for_inner_widget(spin)
            if row < 0:
                return
            price_item = self.tblCart.item(row, 2)
            row_total_item = self.tblCart.item(row, 3)
            if price_item is None or row_total_item is None:
                return
            try:
                unit_price = Decimal(price_item.text())
            except Exception:
                unit_price = Decimal("0")
            quantity = Decimal(str(value))
            if self._return_mode:
                quantity = -quantity
            row_total = quantity * unit_price
            self._updating_cart_items = True
            row_total_item.setText(self._format_money(row_total))
            self._updating_cart_items = False
            self._recalculate_total()
        except Exception as e:
            logger.error("Error in _on_quantity_changed_for_spin: %s", e, exc_info=True)

    def _on_cart_context_menu(self, pos: QPoint) -> None:
        try:
            index = self.tblCart.indexAt(pos)
            if not index.isValid():
                return

            row = index.row()
            if row < 0:
                return

            menu = QMenu(self)
            action_delete = menu.addAction("حذف کالا")
            action_set_qty = menu.addAction("تغییر تعداد")

            global_pos = self.tblCart.viewport().mapToGlobal(pos)
            chosen_action = menu.exec(global_pos)
            if chosen_action is None:
                return

            if chosen_action == action_delete:
                self._delete_row(row)
            elif chosen_action == action_set_qty:
                spin = self._get_quantity_spinbox(row)
                if spin is not None:
                    spin.setFocus()
        except Exception as e:
            logger.error("Error in _on_cart_context_menu: %s", e, exc_info=True)

    def _collect_cart_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        for row in range(self.tblCart.rowCount()):
            name_item = self.tblCart.item(row, 0)
            price_item = self.tblCart.item(row, 2)

            if name_item is None or price_item is None:
                continue

            prod_id = name_item.data(Qt.ItemDataRole.UserRole)
            if prod_id is None:
                continue

            spin = self._get_quantity_spinbox(row)
            if spin is None:
                continue

            try:
                quantity = Decimal(str(spin.value()))
                if self._return_mode:
                    quantity = -quantity
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
            self._current_subtotal = Decimal("0")
            self._current_manual_discount = Decimal("0")
            self._loyalty_points_to_redeem = 0
            self._loyalty_discount_value = Decimal("0")
            self._current_total_amount = Decimal("0")
            self._reset_total()
            return

        subtotal = self._controller.calculate_cart_total(cart_items)
        self._current_subtotal = subtotal

        # Handle manual discount logic
        discount_value = Decimal("0")
        if (
                not self._return_mode
                and hasattr(self, "spinDiscount")
                and self.spinDiscount is not None
                and self.spinDiscount.isEnabled()
        ):
            try:
                discount_value = Decimal(str(self.spinDiscount.value()))
            except Exception:
                discount_value = Decimal("0")

            if discount_value < 0:
                discount_value = Decimal("0")

            # Cap discount at subtotal to avoid negative totals
            if subtotal >= 0 and discount_value > subtotal:
                discount_value = subtotal
                try:
                    self.spinDiscount.blockSignals(True)
                    self.spinDiscount.setValue(float(discount_value))
                    self.spinDiscount.blockSignals(False)
                except Exception:
                    pass
        else:
            # In return mode, force discount to zero
            if hasattr(self, "spinDiscount") and self.spinDiscount is not None:
                try:
                    self.spinDiscount.blockSignals(True)
                    self.spinDiscount.setValue(0.0)
                    self.spinDiscount.blockSignals(False)
                except Exception:
                    pass
            discount_value = Decimal("0")

        self._current_manual_discount = discount_value

        # Loyalty discount logic
        loyalty_discount = Decimal("0")
        points_to_use = 0

        if (
                not self._return_mode
                and self._selected_customer_id is not None
                and hasattr(self, "spinRedeemPoints")
                and self.spinRedeemPoints is not None
                and self.spinRedeemPoints.isEnabled()
        ):
            try:
                requested_points = int(self.spinRedeemPoints.value())
            except Exception:
                requested_points = 0

            if requested_points < 0:
                requested_points = 0

            base_total_for_loyalty = (subtotal - discount_value).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            if base_total_for_loyalty > 0 and requested_points > 0:
                try:
                    max_points, _ = self._controller.calculate_max_redeemable_discount(
                        self._selected_customer_id,
                        base_total_for_loyalty,
                    )
                except Exception as exc:
                    logger.error(
                        "Error calculating max redeemable discount: %s",
                        exc,
                        exc_info=True,
                    )
                    max_points = 0

                points_to_use = min(requested_points, max_points)
                if points_to_use > 0:
                    try:
                        loyalty_discount = (
                                Decimal(points_to_use) * Decimal(str(LOYALTY_POINT_VALUE))
                        )
                    except Exception:
                        loyalty_discount = Decimal("0")

                # Clamp spin box to effective points_to_use
                try:
                    self.spinRedeemPoints.blockSignals(True)
                    if max_points < 0:
                        max_points = 0
                    self.spinRedeemPoints.setMaximum(max_points)
                    self.spinRedeemPoints.setValue(points_to_use)
                    self.spinRedeemPoints.blockSignals(False)
                except Exception:
                    pass
            else:
                points_to_use = 0
                loyalty_discount = Decimal("0")
        else:
            points_to_use = 0
            loyalty_discount = Decimal("0")
            if hasattr(self, "spinRedeemPoints") and self.spinRedeemPoints is not None:
                try:
                    self.spinRedeemPoints.blockSignals(True)
                    self.spinRedeemPoints.setValue(0)
                    self.spinRedeemPoints.blockSignals(False)
                except Exception:
                    pass

        self._loyalty_points_to_redeem = points_to_use
        self._loyalty_discount_value = loyalty_discount

        total = (subtotal - discount_value - loyalty_discount).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        self._current_total_amount = total

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
                self._translator["dialog.info_title"],
                self._translator["shift.info.started"].format(shift_id=shift_id),
            )
        except Exception as e:
            logger.error("Error in ensure_active_shift: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(e),
            )

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

            # In normal sale mode, enforce stock check. In return mode, we allow adding regardless of stock.
            if not self._return_mode and total_stock_dec <= 0:
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

            # Ensure totals and loyalty calculations are up to date
            self._recalculate_total()

            subtotal = self._current_subtotal
            manual_discount = self._current_manual_discount
            loyalty_discount = self._loyalty_discount_value
            total = self._current_total_amount

            discount_for_invoice = (manual_discount + loyalty_discount).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            logger.info(
                "Calculated checkout total: subtotal=%s, manual_discount=%s, loyalty_discount=%s, final=%s, points_to_redeem=%s",
                subtotal,
                manual_discount,
                loyalty_discount,
                total,
                self._loyalty_points_to_redeem,
            )

            shift_id = self._resolve_shift_id()

            success = self._controller.process_checkout(
                shift_id=shift_id,
                cart_items=cart_items,
                total_amount=total,
                payment_method="Cash",
                cust_id=self._selected_customer_id,
                is_refund=self._return_mode,
                discount_amount=discount_for_invoice,
                loyalty_points_to_use=self._loyalty_points_to_redeem,
            )

            if success:
                logger.info(
                    "Checkout completed successfully. ShiftID=%s, Total=%s",
                    shift_id,
                    total,
                )

                # Compute loyalty summary for receipt (view-side, to avoid extra DB round-trip)
                points_spent = 0
                points_earned = 0
                new_balance = None

                if (
                        not self._return_mode
                        and self._selected_customer_id is not None
                        and self._loyalty_points_balance is not None
                ):
                    try:
                        base_balance = max(int(self._loyalty_points_balance or 0), 0)
                    except Exception:
                        base_balance = 0

                    points_spent = max(int(self._loyalty_points_to_redeem or 0), 0)

                    net_total = total
                    if net_total < 0:
                        net_total = Decimal("0")

                    if net_total > 0 and LOYALTY_EARN_THRESHOLD > 0:
                        try:
                            blocks = int(
                                net_total
                                // Decimal(str(LOYALTY_EARN_THRESHOLD))
                            )
                        except Exception:
                            blocks = 0
                        if blocks > 0 and LOYALTY_EARN_RATE > 0:
                            points_earned = blocks * LOYALTY_EARN_RATE

                    new_balance = base_balance - points_spent + points_earned
                    if new_balance < 0:
                        new_balance = 0

                    self._loyalty_points_balance = new_balance
                    self._update_loyalty_label()

                self._generate_receipt_pdf(
                    cart_items,
                    total,
                    points_spent=points_spent,
                    points_earned=points_earned,
                    loyalty_balance_after=new_balance,
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

    def has_active_shift(self) -> bool:
        return self._active_shift_id is not None

    def close_shift(self) -> None:
        """
        Close the active shift using the CloseShiftDialog reconciliation
        workflow.

        Intended for use by both the main window during application shutdown
        and the explicit "Close Shift" button in the Sales view.
        """
        try:
            if self._active_shift_id is None:
                return

            dialog = CloseShiftDialog(
                translation_manager=self._translator,
                controller=self._controller,
                shift_id=self._active_shift_id,
                parent=self,
            )
            result = dialog.exec()
            if result != QDialog.DialogCode.Accepted:
                logger.info("CloseShiftDialog cancelled by user.")
                return

            counted_cash = dialog.counted_cash

            summary = self._controller.close_shift(
                self._active_shift_id,
                counted_cash=counted_cash,
            )
            try:
                self._generate_shift_report_pdf(summary)
            except Exception as inner_exc:
                logger.error(
                    "Error generating shift report PDF during close_shift: %s",
                    inner_exc,
                    exc_info=True,
                )

            self._clear_cart()
            self._active_shift_id = None

            try:
                self.shift_closed.emit(summary)
            except Exception:
                # Emitting the signal must not break the workflow.
                logger.debug("Failed to emit shift_closed signal.", exc_info=True)

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator["shift.close_report_title"],
            )
        except ValueError as e:
            logger.error("Validation error in close_shift: %s", e, exc_info=True)
            QMessageBox.warning(
                self,
                self._translator["dialog.warning_title"],
                str(e),
            )
        except Exception as e:
            logger.error("Error in close_shift: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(e),
            )

    def _on_close_shift_clicked(self) -> None:
        try:
            logger.info("Close Shift button clicked.")

            if self._active_shift_id is None:
                QMessageBox.warning(
                    self,
                    self._translator["dialog.warning_title"],
                    self._translator["shift.info.no_active_shift"],
                )
                return

            # The CloseShiftDialog already contains a confirmation button,
            # so we directly invoke the close_shift workflow here.
            self.close_shift()
        except Exception as e:
            logger.error("Error in _on_close_shift_clicked: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                str(e),
            )

    def _build_shift_report_html(self, summary: Dict[str, Any]) -> str:
        try:
            shift_id = summary.get("shift_id")
            total_sales = summary.get("total_sales", Decimal("0"))
            invoice_count = summary.get("invoice_count", 0)
            cash_float = summary.get("cash_float", Decimal("0"))
            final_balance = summary.get("final_balance")
            start_cash = summary.get("start_cash", Decimal("0"))
            start_time = summary.get("start_time")
            end_time = summary.get("end_time")
            employee_name = summary.get("employee_name") or (
                getattr(self._current_user, "Username", "")
                if self._current_user is not None
                else ""
            )
            items = summary.get("items") or []

            def _fmt_money(value: Any) -> str:
                try:
                    dec_value = (
                        value
                        if isinstance(value, Decimal)
                        else Decimal(str(value or "0"))
                    )
                except Exception:
                    dec_value = Decimal("0")
                return f"{float(dec_value.quantize(Decimal('0.01'))):,.2f}"

            def _fmt_datetime(value: Any) -> str:
                try:
                    if hasattr(value, "strftime"):
                        return value.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
                return "-" if value is None else str(value)

            if final_balance is None:
                final_balance = start_cash + total_sales

            rows_html = ""
            for index, item in enumerate(items, start=1):
                name = item.get("name", "")
                quantity = item.get("quantity", 0)
                total = item.get("total", Decimal("0"))

                try:
                    quantity_dec = Decimal(str(quantity))
                    quantity_str = f"{float(quantity_dec):,.2f}"
                except Exception:
                    quantity_str = str(quantity)

                rows_html += f"""
                    <tr>
                        <td>{index}</td>
                        <td>{name}</td>
                        <td>{quantity_str}</td>
                        <td>{_fmt_money(total)}</td>
                    </tr>
                """

            title = self._translator["shift.close_report_title"]
            summary_title = self._translator["shift.report.summary_title"]
            items_title = self._translator["shift.report.items_title"]

            label_shift_id = self._translator["shift.report.label.shift_id"]
            label_employee = self._translator["shift.report.label.employee"]
            label_start_time = self._translator["shift.report.label.start_time"]
            label_end_time = self._translator["shift.report.label.end_time"]
            label_cash_float = self._translator["shift.report.label.cash_float"]
            label_total_sales = self._translator["shift.report.label.total_sales"]
            label_order_count = self._translator["shift.report.label.order_count"]
            label_final_balance = self._translator["shift.report.label.final_balance"]

            header_name = self._translator["shift.report.table.header.name"]
            header_quantity = self._translator["shift.report.table.header.quantity"]
            header_total = self._translator["shift.report.table.header.total"]

            html = f"""
            <html dir="rtl">
              <head>
                <meta charset="utf-8" />
                <style>
                    body {{
                        font-family: 'Tahoma', 'Vazirmatn', sans-serif;
                        font-size: 10pt;
                        direction: rtl;
                    }}
                    h1 {{
                        font-size: 14pt;
                        margin-bottom: 8px;
                        text-align: center;
                    }}
                    h2 {{
                        font-size: 12pt;
                        margin-top: 16px;
                        margin-bottom: 6px;
                    }}
                    table {{
                        border-collapse: collapse;
                        width: 100%;
                    }}
                    th, td {{
                        border: 1px solid black;
                        padding: 8px;
                        text-align: center;
                    }}
                    th {{
                        background-color: #0f172a;
                        color: #f9fafb;
                    }}
                </style>
              </head>
              <body>
                <h1>{title}</h1>

                <h2>{summary_title}</h2>
                <table>
                  <tr>
                    <th>{label_shift_id}</th>
                    <td>{shift_id}</td>
                    <th>{label_employee}</th>
                    <td>{employee_name}</td>
                  </tr>
                  <tr>
                    <th>{label_start_time}</th>
                    <td>{_fmt_datetime(start_time)}</td>
                    <th>{label_end_time}</th>
                    <td>{_fmt_datetime(end_time)}</td>
                  </tr>
                  <tr>
                    <th>{label_cash_float}</th>
                    <td>{_fmt_money(cash_float)}</td>
                    <th>{label_total_sales}</th>
                    <td>{_fmt_money(total_sales)}</td>
                  </tr>
                  <tr>
                    <th>{label_order_count}</th>
                    <td>{invoice_count}</td>
                    <th>{label_final_balance}</th>
                    <td>{_fmt_money(final_balance)}</td>
                  </tr>
                </table>

                <h2>{items_title}</h2>
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{header_name}</th>
                      <th>{header_quantity}</th>
                      <th>{header_total}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows_html}
                  </tbody>
                </table>
              </body>
            </html>
            """
            return html
        except Exception as e:
            logger.error("Error while building shift report HTML: %s", e, exc_info=True)
            return f"<html><body><pre>{summary}</pre></body></html>"

    def _generate_shift_report_pdf(self, summary: Dict[str, Any]) -> None:
        try:
            if not summary:
                return

            html = self._build_shift_report_html(summary)

            default_filename = f"shift_{summary.get('shift_id', 'report')}.pdf"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                self._translator["shift.report.save_dialog_title"],
                default_filename,
                "PDF Files (*.pdf)",
            )
            if not filename:
                logger.info("User cancelled saving shift report PDF.")
                return

            document = QTextDocument()
            document.setHtml(html)

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(filename)

            document.print(printer)

            QMessageBox.information(
                self,
                self._translator["dialog.info_title"],
                self._translator["shift.report.info.saved"].format(path=filename),
            )
        except Exception as e:
            logger.error("Error generating shift report PDF: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                self._translator["dialog.error_title"],
                self._translator["shift.report.error.save_failed"].format(
                    details=str(e)
                ),
            )

    def _build_receipt_html(
            self,
            cart_items: List[Dict[str, Any]],
            total: Decimal,
            subtotal: Optional[Decimal] = None,
            discount: Optional[Decimal] = None,
            is_refund: bool = False,
            loyalty_discount: Optional[Decimal] = None,
            points_spent: int = 0,
            points_earned: int = 0,
            loyalty_balance_after: Optional[int] = None,
    ) -> str:
        """
        Build HTML for the sales/return receipt.

        Uses a single triple-quoted f-string for the main document and avoids
        backslash-based line continuations to keep syntax simple and robust.
        """
        try:
            lines_html = ""
            for item in cart_items:
                name = str(item.get("Name", ""))
                qty = item.get("Quantity", Decimal("0"))
                unit_price = item.get("UnitPrice", Decimal("0"))
                try:
                    qty_dec = qty if isinstance(qty, Decimal) else Decimal(str(qty or "0"))
                except Exception:
                    qty_dec = Decimal("0")
                try:
                    price_dec = (
                        unit_price
                        if isinstance(unit_price, Decimal)
                        else Decimal(str(unit_price or "0"))
                    )
                except Exception:
                    price_dec = Decimal("0")

                line_total = (qty_dec * price_dec) if qty_dec and price_dec else Decimal("0")
                lines_html += f"""
                <tr>
                  <td>{name}</td>
                  <td style="text-align:center;">{qty_dec}</td>
                  <td style="text-align:right;">{self._format_money(price_dec)}</td>
                  <td style="text-align:right;">{self._format_money(line_total)}</td>
                </tr>
                """

            customer_line = self._selected_customer_name or "-"

            if subtotal is None:
                subtotal = total
            if discount is None:
                discount = Decimal("0")

            title_sale = self._translator["sales.receipt.title_sale"]
            title_refund = self._translator["sales.receipt.title_refund"]
            tx_title = title_refund if is_refund else title_sale

            customer_label = self._translator["sales.receipt.customer_label"]
            subtotal_label = self._translator["sales.receipt.subtotal_label"]
            discount_label = self._translator["sales.receipt.discount_label"]
            total_label = self._translator["sales.receipt.total_label"]

            loyalty_discount_label = self._translator.get(
                "sales.receipt.loyalty_discount_label",
                "Loyalty Discount",
            )
            loyalty_points_spent_label = self._translator.get(
                "sales.receipt.loyalty_points_spent_label",
                "used {points} pts",
            )
            loyalty_points_earned_label = self._translator.get(
                "sales.receipt.loyalty_points_earned_label",
                "Points Earned",
            )
            loyalty_balance_label = self._translator.get(
                "sales.receipt.loyalty_balance_label",
                "Current Balance",
            )

            col_name = self._translator["sales.receipt.table.header.name"]
            col_qty = self._translator["sales.receipt.table.header.quantity"]
            col_price = self._translator["sales.receipt.table.header.price"]
            col_total = self._translator["sales.receipt.table.header.total"]

            if loyalty_discount is None:
                loyalty_discount = Decimal("0")

            show_loyalty_discount = points_spent > 0 and loyalty_discount > 0
            show_points_earned = points_earned > 0
            show_balance = loyalty_balance_after is not None

            loyalty_lines: list[str] = []
            if show_loyalty_discount:
                loyalty_lines.append(
                    f'<div class="meta">'
                    f'{loyalty_discount_label}: -{self._format_money(loyalty_discount)} '
                    f'({loyalty_points_spent_label.format(points=points_spent)})'
                    f"</div>"
                )

            if show_points_earned:
                loyalty_lines.append(
                    f'<div class="meta" style="font-weight:bold;">'
                    f"{loyalty_points_earned_label}: +{points_earned}"
                    f"</div>"
                )

            if show_balance:
                loyalty_lines.append(
                    f'<div class="meta">'
                    f"{loyalty_balance_label}: {loyalty_balance_after} pts"
                    f"</div>"
                )

            loyalty_html = "\n".join(loyalty_lines)

            html = f"""
            <html dir="rtl">
              <head>
                <meta charset="utf-8" />
                <style>
                  @page {{
                    size: 80mm auto;
                    margin: 4mm;
                  }}
                  body {{
                    width: 80mm;
                    font-family: 'Tahoma', 'Vazirmatn', sans-serif;
                    font-size: 9pt;
                    direction: rtl;
                  }}
                  h1 {{
                    font-size: 11pt;
                    text-align: center;
                    margin: 0 0 4px 0;
                  }}
                  table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 4px;
                  }}
                  th, td {{
                    border-bottom: 1px dashed #999;
                    padding: 2px 0;
                  }}
                  th {{
                    text-align: center;
                  }}
                  .total-row td {{
                    border-top: 1px solid #000;
                    font-weight: bold;
                  }}
                  .meta {{
                    font-size: 8pt;
                    margin-top: 2px;
                  }}
                </style>
              </head>
              <body>
                <h1>{tx_title}</h1>
                <div class="meta">{customer_label}: {customer_line}</div>
                <table>
                  <thead>
                    <tr>
                      <th>{col_name}</th>
                      <th>{col_qty}</th>
                      <th>{col_price}</th>
                      <th>{col_total}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lines_html}
                    <tr>
                      <td colspan="3" style="text-align:left;">{subtotal_label}</td>
                      <td style="text-align:right;">{self._format_money(subtotal)}</td>
                    </tr>
                    <tr>
                      <td colspan="3" style="text-align:left;">{discount_label}</td>
                      <td style="text-align:right;">{self._format_money(discount)}</td>
                    </tr>
                    <tr class="total-row">
                      <td colspan="3" style="text-align:left;">{total_label}</td>
                      <td style="text-align:right;">{self._format_money(total)}</td>
                    </tr>
                  </tbody>
                </table>
                {loyalty_html}
              </body>
            </html>
            """
            return html
        except Exception as e:
            logger.error("Error while building receipt HTML: %s", e, exc_info=True)
            return "<html><body><pre>Receipt error</pre></body></html>"

    def _generate_receipt_pdf(
            self,
            cart_items: List[Dict[str, Any]],
            total: Decimal,
            points_spent: int = 0,
            points_earned: int = 0,
            loyalty_balance_after: Optional[int] = None,
    ) -> None:
        try:
            if not cart_items:
                return

            # Enrich with product names for receipt
            enriched_items: List[Dict[str, Any]] = []
            for row in range(self.tblCart.rowCount()):
                name_item = self.tblCart.item(row, 0)
                if name_item is None:
                    continue
                spin = self._get_quantity_spinbox(row)
                price_item = self.tblCart.item(row, 2)
                if spin is None or price_item is None:
                    continue
                try:
                    qty = Decimal(str(spin.value()))
                    if self._return_mode:
                        qty = -qty
                except Exception:
                    qty = Decimal("0")
                try:
                    unit_price = Decimal(price_item.text())
                except Exception:
                    unit_price = Decimal("0")
                enriched_items.append(
                    {
                        "Name": name_item.text(),
                        "Quantity": qty,
                        "UnitPrice": unit_price,
                    }
                )

            # Use cached subtotal / discounts when available to keep receipt consistent
            subtotal = self._current_subtotal
            if subtotal == Decimal("0"):
                subtotal = self._controller.calculate_cart_total(enriched_items)

            discount_value = (self._current_manual_discount + self._loyalty_discount_value).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            html = self._build_receipt_html(
                enriched_items,
                total,
                subtotal=subtotal,
                discount=discount_value,
                is_refund=self._return_mode,
                loyalty_discount=self._loyalty_discount_value,
                points_spent=points_spent,
                points_earned=points_earned,
                loyalty_balance_after=loyalty_balance_after,
            )

            default_filename = "receipt.pdf"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                self._translator.get(
                    "sales.receipt.save_dialog_title",
                    "Save sales receipt as PDF",
                ),
                default_filename,
                "PDF Files (*.pdf)",
            )
            if not filename:
                logger.info("User cancelled saving sales receipt PDF.")
                return

            document = QTextDocument()
            document.setHtml(html)

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(filename)
            # Configure page size to 80mm width
            margins = QMarginsF(2, 2, 2, 2)
            printer.setPageMargins(margins, QPageLayout.Unit.Millimeter)

            document.print(printer)
        except Exception as e:
            logger.error("Error generating receipt PDF: %s", e, exc_info=True)

    def _load_cart_from_items(self, items: List[Dict[str, Any]]) -> None:
        try:
            self._clear_cart()
            for item in items:
                try:
                    prod_id = int(item.get("ProdID"))
                except Exception:
                    continue
                name = str(item.get("Name", ""))
                unit_price = Decimal(str(item.get("UnitPrice", "0")))
                quantity = Decimal(str(item.get("Quantity", "0")))
                if quantity <= 0:
                    quantity = abs(quantity)

                row = self.tblCart.rowCount()
                self.tblCart.insertRow(row)

                name_item = QTableWidgetItem(name)
                name_item.setData(Qt.ItemDataRole.UserRole, prod_id)
                name_item.setFlags(
                    name_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )

                price_item = QTableWidgetItem(self._format_money(unit_price))
                price_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
                )
                price_item.setFlags(
                    price_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )

                row_total = unit_price * quantity
                row_total_item = QTableWidgetItem(
                    self._format_money(row_total)
                )
                row_total_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
                )
                row_total_item.setFlags(
                    row_total_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )

                self.tblCart.setItem(row, 0, name_item)
                self.tblCart.setItem(row, 2, price_item)
                self.tblCart.setItem(row, 3, row_total_item)

                spin = QSpinBox(self.tblCart)
                spin.setMinimum(1)
                spin.setMaximum(1000000)
                spin.setValue(int(quantity))
                spin.setFixedSize(60, 35)
                spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spin.setPrefix("-" if self._return_mode else "")
                spin.valueChanged.connect(
                    lambda value, s=spin: self._on_quantity_changed_for_spin(
                        s, value
                    )
                )

                qty_container = QWidget(self.tblCart)
                qty_layout = QHBoxLayout(qty_container)
                qty_layout.setContentsMargins(0, 0, 0, 0)
                qty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                qty_layout.addWidget(spin)
                self.tblCart.setCellWidget(row, 1, qty_container)

                btn_delete = QPushButton("X", self.tblCart)
                btn_delete.setFixedSize(28, 28)
                btn_delete.setStyleSheet(
                    "QPushButton { background-color: #dc2626; color: #ffffff; border: none; border-radius: 4px; }"
                    "QPushButton:hover { background-color: #b91c1c; }"
                )
                btn_delete.clicked.connect(
                    lambda _, b=btn_delete: self._delete_row_for_button(b)
                )

                del_container = QWidget(self.tblCart)
                del_layout = QHBoxLayout(del_container)
                del_layout.setContentsMargins(0, 0, 0, 0)
                del_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                del_layout.addWidget(btn_delete)
                self.tblCart.setCellWidget(row, 4, del_container)

            self._recalculate_total()
        except Exception as e:
            logger.error("Error in _load_cart_from_items: %s", e, exc_info=True)

    def _clear_cart(self) -> None:
        self.tblCart.setRowCount(0)
        self._reset_total()
        self.txtBarcode.clear()
        self.txtBarcode.setFocus()
