from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.controllers.sales_controller import SalesController
from app.core.translation_manager import TranslationManager

logger = logging.getLogger(__name__)


class CloseShiftDialog(QDialog):
    """
    Dialog for closing a shift with cash reconciliation.

    It displays:
        * Start cash (float),
        * Total cash sales,
        * Total card sales,
        * System-expected cash in drawer,
    and lets the cashier enter the physically counted cash. A variance
    label shows Counted - Expected and changes color depending on overage
    / shortage / match.
    """

    def __init__(
        self,
        translation_manager: TranslationManager,
        controller: SalesController,
        shift_id: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translation_manager
        self._controller = controller
        self._shift_id = shift_id

        self._totals: Dict[str, Any] = {}
        self._counted_cash: Decimal = Decimal("0.00")
        self._expected_cash: Decimal = Decimal("0.00")
        self._variance: Decimal = Decimal("0.00")

        try:
            self._load_totals()
            self._build_ui()
            self._apply_translations()
            self._populate_totals()
            self._recalculate_variance()
        except Exception as exc:
            logger.error("Error initializing CloseShiftDialog: %s", exc, exc_info=True)
            raise

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _tr(self, key: str, default: str) -> str:
        try:
            return self._translator.get(key, default)
        except Exception:
            return default

    def _parse_decimal(self, value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        except Exception:
            return Decimal("0.00")

    def _load_totals(self) -> None:
        totals = self._controller.calculate_shift_totals(self._shift_id)
        self._totals = totals or {}

        self._expected_cash = self._parse_decimal(
            self._totals.get("system_expected_cash", "0")
        )

    def _build_ui(self) -> None:
        self.setModal(True)
        self.setMinimumSize(480, 320)
        self.setWindowTitle(self._tr("shift.close_dialog.title", "Close Shift"))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Description
        description = QLabel(
            self._tr(
                "shift.close_dialog.message",
                "Please count the physical cash in the drawer and enter the amount below.",
            ),
            self,
        )
        description.setWordWrap(True)
        main_layout.addWidget(description)

        # Totals form
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        self.lblStartCash = QLabel(self)
        self.lblCashSales = QLabel(self)
        self.lblCardSales = QLabel(self)
        self.lblSystemExpected = QLabel(self)
        self.lblVariance = QLabel(self)

        # Counted cash input
        self.txtCountedCash = QLineEdit(self)
        self.txtCountedCash.setObjectName("txtCountedCash")
        validator = QDoubleValidator(self)
        validator.setBottom(0.0)
        self.txtCountedCash.setValidator(validator)

        form.addRow(
            self._tr("shift.close_dialog.start_cash", "Start cash:"),
            self.lblStartCash,
        )
        form.addRow(
            self._tr("shift.close_dialog.cash_sales", "Cash sales:"),
            self.lblCashSales,
        )
        form.addRow(
            self._tr("shift.close_dialog.card_sales", "Card sales:"),
            self.lblCardSales,
        )
        form.addRow(
            self._tr("shift.close_dialog.system_expected", "System expected cash:"),
            self.lblSystemExpected,
        )

        counted_row = QHBoxLayout()
        counted_row.setSpacing(4)
        counted_row.addWidget(self.txtCountedCash)
        form.addRow(
            self._tr("shift.close_dialog.counted_cash", "Counted cash:"),
            counted_row,
        )

        form.addRow(
            self._tr("shift.close_dialog.variance", "Variance (Counted - Expected):"),
            self.lblVariance,
        )

        main_layout.addLayout(form)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        main_layout.addWidget(button_box)

        # Customize button text
        btn_ok = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if btn_ok is not None:
            btn_ok.setText(
                self._tr(
                    "shift.close_dialog.confirm_button",
                    "Confirm & Close Shift",
                )
            )

        btn_cancel = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if btn_cancel is not None:
            btn_cancel.setText(
                self._tr("shift.close_dialog.cancel_button", "Cancel")
            )

        # Signals
        self.txtCountedCash.textChanged.connect(self._on_counted_cash_changed)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

    def _apply_translations(self) -> None:
        # The main window title and labels are already created using _tr,
        # so nothing additional is strictly required here. This method
        # is kept for symmetry with other dialogs.
        self._update_variance_label_style()

    def _format_money(self, value: Any) -> str:
        dec = self._parse_decimal(value)
        return f"{float(dec):,.2f}"

    def _populate_totals(self) -> None:
        start_cash = self._parse_decimal(self._totals.get("start_cash"))
        cash_sales = self._parse_decimal(self._totals.get("total_cash_sales"))
        card_sales = self._parse_decimal(self._totals.get("total_card_sales"))
        expected = self._parse_decimal(self._totals.get("system_expected_cash"))

        self._expected_cash = expected

        self.lblStartCash.setText(self._format_money(start_cash))
        self.lblCashSales.setText(self._format_money(cash_sales))
        self.lblCardSales.setText(self._format_money(card_sales))
        self.lblSystemExpected.setText(self._format_money(expected))

        # Pre-fill counted cash with expected value as a visual hint.
        self.txtCountedCash.setText(self._format_money(expected))

    # ------------------------------------------------------------------ #
    # Variance handling
    # ------------------------------------------------------------------ #
    def _on_counted_cash_changed(self, _text: str) -> None:
        self._recalculate_variance()

    def _recalculate_variance(self) -> None:
        text = (self.txtCountedCash.text() or "").replace(",", "").strip()
        try:
            counted = Decimal(text or "0").quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        except Exception:
            counted = Decimal("0.00")

        self._counted_cash = counted

        variance = (counted - self._expected_cash).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        self._variance = variance

        # Update label text
        if variance == 0:
            variance_text = self._tr(
                "shift.close_dialog.variance_ok",
                "0.00 (Matched)",
            )
        elif variance < 0:
            shortage = -variance
            variance_text = self._tr(
                "shift.close_dialog.variance_short",
                "Shortage: {amount}",
            ).format(amount=self._format_money(shortage))
        else:
            variance_text = self._tr(
                "shift.close_dialog.variance_over",
                "Overage: {amount}",
            ).format(amount=self._format_money(variance))

        self.lblVariance.setText(variance_text)
        self._update_variance_label_style()

    def _update_variance_label_style(self) -> None:
        """
        Color the variance label based on its sign:
            * Green for 0 (matched),
            * Red for negative (shortage),
            * Blue for positive (overage).
        """
        variance = getattr(self, "_variance", Decimal("0.00"))

        if variance == 0:
            color = "#15803d"  # green
        elif variance < 0:
            color = "#b91c1c"  # red
        else:
            color = "#2563eb"  # blue

        self.lblVariance.setStyleSheet(f"color: {color}; font-weight: bold;")

    # ------------------------------------------------------------------ #
    # Accept / public API
    # ------------------------------------------------------------------ #
    def _on_accept(self) -> None:
        text = (self.txtCountedCash.text() or "").replace(",", "").strip()
        if not text:
            QMessageBox.warning(
                self,
                self._tr("dialog.warning_title", "Warning"),
                self._tr(
                    "shift.close_dialog.error.no_counted_cash",
                    "Please enter the counted cash amount.",
                ),
            )
            return

        try:
            counted = Decimal(text).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        except Exception:
            QMessageBox.warning(
                self,
                self._tr("dialog.warning_title", "Warning"),
                self._tr(
                    "shift.close_dialog.error.invalid_counted_cash",
                    "Invalid counted cash amount.",
                ),
            )
            return

        if counted < 0:
            QMessageBox.warning(
                self,
                self._tr("dialog.warning_title", "Warning"),
                self._tr(
                    "shift.close_dialog.error.negative_counted_cash",
                    "Counted cash cannot be negative.",
                ),
            )
            return

        self._counted_cash = counted
        self.accept()

    @property
    def counted_cash(self) -> Decimal:
        """
        Return the validated counted cash amount entered by the user.
        """
        return self._counted_cash

    @property
    def expected_cash(self) -> Decimal:
        return self._expected_cash

    @property
    def variance(self) -> Decimal:
        return self._variance