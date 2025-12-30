from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Iterable, Mapping, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import (
    InventoryBatch,
    Invoice,
    InvoiceItem,
    Payment,
    Product,
    Shift,
)

SessionFactory = Callable[[], Session]

logger = logging.getLogger(__name__)


class SalesController:
    """
    Business logic for the Sales / POS module.

    Provides product lookup, cart total calculation, manual shift management,
    transactional checkout with FIFO (expiry-date based) inventory deduction,
    and simple dashboard statistics.
    """

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory: SessionFactory = session_factory or SessionLocal

    def _get_session(self) -> Session:
        return self._session_factory()

    # --------------------------------------------------------------------- #
    # Product lookup
    # --------------------------------------------------------------------- #
    def get_product_details(self, barcode: str) -> Optional[dict]:
        """
        Fetch basic product information and aggregated stock for a barcode.

        Returns a dictionary:
            {
                "ProdID": int,
                "Name": str,
                "Barcode": str,
                "BasePrice": Decimal,
                "TotalStock": Decimal,
            }

        or None if the product does not exist.
        """
        try:
            if not barcode:
                logger.info(
                    "get_product_details called with empty barcode; ignoring request."
                )
                return None

            barcode = barcode.strip()
            logger.info("Searching for barcode: '%s'", barcode)

            with self._get_session() as session:
                # Primary lookup: exact match on trimmed barcode
                result = (
                    session.query(
                        Product.ProdID,
                        Product.Name,
                        Product.Barcode,
                        Product.BasePrice,
                        func.coalesce(
                            func.sum(InventoryBatch.CurrentQuantity),
                            0,
                        ).label("TotalStock"),
                    )
                    .outerjoin(
                        InventoryBatch,
                        InventoryBatch.ProdID == Product.ProdID,
                    )
                    .filter(func.trim(Product.Barcode) == barcode)
                    .group_by(Product.ProdID)
                    .first()
                )

                # Fallback: try a case-insensitive match if exact lookup failed
                if result is None:
                    logger.info(
                        "Exact barcode match failed for '%s'; trying case-insensitive lookup.",
                        barcode,
                    )
                    result = (
                        session.query(
                            Product.ProdID,
                            Product.Name,
                            Product.Barcode,
                            Product.BasePrice,
                            func.coalesce(
                                func.sum(InventoryBatch.CurrentQuantity),
                                0,
                            ).label("TotalStock"),
                        )
                        .outerjoin(
                            InventoryBatch,
                            InventoryBatch.ProdID == Product.ProdID,
                        )
                        .filter(Product.Barcode.ilike(barcode))
                        .group_by(Product.ProdID)
                        .first()
                    )

                if result is None:
                    logger.warning("No product found for barcode '%s'.", barcode)
                    return None

                prod_id, name, barcode_val, base_price, total_stock = result

                base_price_dec = (
                    Decimal(str(base_price)) if base_price is not None else Decimal("0")
                )
                total_stock_dec = Decimal(str(total_stock))

                logger.info(
                    "Product found for barcode '%s': ProdID=%s, Name='%s', TotalStock=%s",
                    barcode,
                    prod_id,
                    name,
                    total_stock_dec,
                )

                return {
                    "ProdID": prod_id,
                    "Name": name,
                    "Barcode": barcode_val,
                    "BasePrice": base_price_dec,
                    "TotalStock": total_stock_dec,
                }
        except Exception as e:
            logger.error("Error in get_product_details: %s", e, exc_info=True)
            raise

    # --------------------------------------------------------------------- #
    # Cart helpers
    # --------------------------------------------------------------------- #
    def calculate_cart_total(
        self,
        cart_items: Iterable[Mapping[str, Any]],
    ) -> Decimal:
        """
        Calculate the total amount for a collection of cart items.

        Each cart item is expected to be a mapping with at least:
            - 'ProdID'
            - 'Quantity'
            - 'UnitPrice'

        Values are converted to Decimal for accurate financial calculations.
        """
        try:
            items_list = list(cart_items)
            logger.info(
                "Calculating cart total for %d item(s) in SalesController.",
                len(items_list),
            )

            total = Decimal("0")
            for item in items_list:
                qty = Decimal(str(item.get("Quantity", 0)))
                price = Decimal(str(item.get("UnitPrice", 0)))
                total += qty * price

            total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            logger.info("Cart total calculated: %s", total)
            return total
        except Exception as e:
            logger.error("Error in calculate_cart_total: %s", e, exc_info=True)
            raise

    # --------------------------------------------------------------------- #
    # Shift helpers (manual open/close)
    # --------------------------------------------------------------------- #
    def get_active_shift(self, emp_id: Optional[int]) -> Optional[int]:
        """
        Return the currently open shift ID for the given employee, if any.
        """
        try:
            if emp_id is None:
                raise ValueError("Current employee could not be determined.")

            logger.info("Looking up active shift for EmpID=%s.", emp_id)

            with self._get_session() as session:
                shift = (
                    session.query(Shift)
                    .filter(Shift.EmpID == emp_id, Shift.Status == "Open")
                    .order_by(Shift.StartTime.desc())
                    .first()
                )

                if shift is None:
                    logger.info("No active shift found for EmpID=%s.", emp_id)
                    return None

                logger.info(
                    "Active shift found for EmpID=%s: ShiftID=%s",
                    emp_id,
                    shift.ShiftID,
                )
                return shift.ShiftID
        except Exception as e:
            logger.error("Error in get_active_shift: %s", e, exc_info=True)
            raise

    def start_shift(self, emp_id: Optional[int], cash_float: Any) -> int:
        """
        Explicitly create a new shift for *emp_id* with the given cash float.

        Raises ValueError if an active shift already exists for the employee.
        """
        try:
            if emp_id is None:
                raise ValueError("Current employee could not be determined.")

            cash_dec = Decimal(str(cash_float or 0)).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            if cash_dec < 0:
                raise ValueError("Cash float cannot be negative.")

            logger.info(
                "Starting new shift for EmpID=%s with CashFloat=%s.",
                emp_id,
                cash_dec,
            )

            with self._get_session() as session:
                with session.begin():
                    existing = (
                        session.query(Shift)
                        .filter(Shift.EmpID == emp_id, Shift.Status == "Open")
                        .order_by(Shift.StartTime.desc())
                        .first()
                    )
                    if existing is not None:
                        raise ValueError(
                            f"An open shift (ShiftID={existing.ShiftID}) already exists "
                            f"for employee {emp_id}."
                        )

                    shift = Shift(
                        EmpID=emp_id,
                        StartCash=cash_dec,
                        CashFloat=cash_dec,
                        Status="Open",
                    )
                    session.add(shift)
                    session.flush()
                    logger.info(
                        "New shift created: ShiftID=%s for EmpID=%s.",
                        shift.ShiftID,
                        emp_id,
                    )
                    return shift.ShiftID
        except Exception as e:
            logger.error("Error in start_shift: %s", e, exc_info=True)
            raise

    def close_shift(self, shift_id: int) -> dict:
        """
        Close the given shift and return a summary dictionary:

            {
                "shift_id": int,
                "total_sales": Decimal,
                "invoice_count": int,
            }
        """
        try:
            logger.info("Closing shift ShiftID=%s.", shift_id)

            with self._get_session() as session:
                with session.begin():
                    shift = session.get(Shift, shift_id)
                    if shift is None:
                        raise ValueError(f"Shift {shift_id} not found.")

                    if shift.Status == "Closed":
                        logger.warning(
                            "close_shift called for already closed ShiftID=%s.",
                            shift_id,
                        )

                    total_sales_raw, invoice_count = (
                        session.query(
                            func.coalesce(func.sum(Invoice.TotalAmount), 0),
                            func.count(Invoice.InvID),
                        )
                        .filter(
                            Invoice.ShiftID == shift_id,
                            Invoice.Status != "Void",
                        )
                        .one()
                    )

                    total_sales = Decimal(str(total_sales_raw or 0)).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                    invoice_count_int = int(invoice_count or 0)

                    start_cash = (
                        Decimal(str(shift.StartCash))
                        if shift.StartCash is not None
                        else Decimal("0")
                    )
                    shift.SystemCalculatedCash = (start_cash + total_sales).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                    shift.EndTime = func.now()
                    shift.Status = "Closed"

                    logger.info(
                        "Shift %s closed. Total sales=%s, invoice_count=%s.",
                        shift_id,
                        total_sales,
                        invoice_count_int,
                    )

                    return {
                        "shift_id": shift_id,
                        "total_sales": total_sales,
                        "invoice_count": invoice_count_int,
                    }
        except Exception as e:
            logger.error("Error in close_shift: %s", e, exc_info=True)
            raise

    # Legacy helper retained for compatibility (not used by the new UI code).
    def get_or_create_active_shift(self, emp_id: Optional[int]) -> int:
        """
        Legacy helper that returns an open shift for the given employee,
        creating one if needed. The new UI uses explicit start_shift instead.
        """
        try:
            active_id = self.get_active_shift(emp_id)
            if active_id is not None:
                return active_id

            # Fallback to creating a shift with zero float for legacy callers.
            logger.info(
                "No active shift found via get_or_create_active_shift; "
                "creating a zero-float shift for EmpID=%s.",
                emp_id,
            )
            return self.start_shift(emp_id, Decimal("0"))
        except Exception as e:
            logger.error("Error in get_or_create_active_shift: %s", e, exc_info=True)
            raise

    # --------------------------------------------------------------------- #
    # Checkout / transactional logic
    # --------------------------------------------------------------------- #
    def process_checkout(
        self,
        shift_id: int,
        cart_items: Iterable[Mapping[str, Any]],
        total_amount: Any,
        payment_method: str = "Cash",
    ) -> bool:
        """
        Perform a complete checkout operation in a single DB transaction.

        Steps:
            * Validate input and recompute cart total.
            * Create Invoice (Status='Paid').
            * Deduct inventory using FIFO (ExpiryDate ascending) per product.
            * Create one or more InvoiceItem rows per product/batch.
            * Create a Payment row linked to the Invoice.

        Raises ValueError for business-rule violations (e.g. insufficient stock
        or missing shift). Any exception aborts the transaction.
        """
        try:
            cart_items_list = list(cart_items)
            if not cart_items_list:
                raise ValueError("Cart is empty.")

            logger.info(
                "Starting checkout: shift_id=%s, items=%d, payment_method=%s",
                shift_id,
                len(cart_items_list),
                payment_method,
            )

            computed_total = self.calculate_cart_total(cart_items_list)

            # total_amount is accepted but not trusted blindly; we base persistence
            # on the computed total.
            _ = total_amount  # kept for signature compatibility

            with self._get_session() as session:
                # session.begin() ensures atomic commit/rollback
                with session.begin():
                    # Validate shift
                    shift = session.get(Shift, shift_id)
                    if shift is None:
                        raise ValueError("Active shift not found.")

                    if shift.Status != "Open":
                        raise ValueError("Cannot perform checkout on a closed shift.")

                    # Create invoice
                    invoice = Invoice(
                        ShiftID=shift_id,
                        CustID=None,
                        TotalAmount=computed_total,
                        Status="Paid",
                    )
                    session.add(invoice)
                    session.flush()  # Ensure InvID is available

                    # Process each cart line
                    for item in cart_items_list:
                        prod_id = int(item["ProdID"])
                        qty = Decimal(str(item["Quantity"]))
                        unit_price = Decimal(str(item["UnitPrice"]))

                        if qty <= 0:
                            logger.info(
                                "Skipping cart line with non-positive quantity: ProdID=%s, Qty=%s",
                                prod_id,
                                qty,
                            )
                            continue

                        # Lock relevant inventory rows (FIFO / FEFO by ExpiryDate)
                        batches = (
                            session.query(InventoryBatch)
                            .filter(
                                InventoryBatch.ProdID == prod_id,
                                InventoryBatch.CurrentQuantity > 0,
                            )
                            .order_by(
                                InventoryBatch.ExpiryDate.asc(),
                                InventoryBatch.BatchID.asc(),
                            )
                            .with_for_update()
                            .all()
                        )

                        available = sum(
                            (Decimal(str(b.CurrentQuantity)) for b in batches),
                            Decimal("0"),
                        )

                        if available < qty:
                            raise ValueError(
                                f"Insufficient stock for product ID {prod_id}. "
                                f"Requested {qty}, available {available}."
                            )

                        remaining = qty

                        for batch in batches:
                            if remaining <= 0:
                                break

                            batch_qty = Decimal(str(batch.CurrentQuantity))
                            if batch_qty <= 0:
                                continue

                            use_qty = min(batch_qty, remaining)
                            new_qty = batch_qty - use_qty

                            batch.CurrentQuantity = new_qty
                            remaining -= use_qty

                            line_total = (use_qty * unit_price).quantize(
                                Decimal("0.01"),
                                rounding=ROUND_HALF_UP,
                            )

                            invoice_item = InvoiceItem(
                                InvID=invoice.InvID,
                                ProdID=prod_id,
                                BatchID=batch.BatchID,
                                Quantity=use_qty,
                                UnitPrice=unit_price,
                                Discount=Decimal("0"),
                                TaxAmount=Decimal("0"),
                                LineTotal=line_total,
                            )
                            session.add(invoice_item)

                        if remaining > 0:
                            # Should not occur due to pre-check, but kept as a guard.
                            raise ValueError(
                                f"Unable to allocate full quantity for product ID {prod_id}."
                            )

                    # Record payment
                    payment = Payment(
                        InvID=invoice.InvID,
                        Amount=computed_total,
                        Method=payment_method,
                        TransactionRef=None,
                    )
                    session.add(payment)

            logger.info(
                "Checkout completed successfully for shift_id=%s, total=%s",
                shift_id,
                computed_total,
            )
            # If we reach here without exception, the transaction was committed.
            return True
        except Exception as e:
            logger.error("Error in process_checkout: %s", e, exc_info=True)
            raise

    # --------------------------------------------------------------------- #
    # Dashboard helpers
    # --------------------------------------------------------------------- #
    def get_today_dashboard_stats(self) -> dict:
        """
        Return today's total sales amount and invoice count:

            {
                "total_sales": Decimal,
                "invoice_count": int,
            }
        """
        try:
            today = date.today()
            logger.info("Calculating dashboard stats for %s.", today)

            with self._get_session() as session:
                total_sales_raw, invoice_count = (
                    session.query(
                        func.coalesce(func.sum(Invoice.TotalAmount), 0),
                        func.count(Invoice.InvID),
                    )
                    .filter(
                        func.date(Invoice.Date) == today,
                        Invoice.Status != "Void",
                    )
                    .one()
                )

                total_sales = Decimal(str(total_sales_raw or 0)).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
                invoice_count_int = int(invoice_count or 0)

                logger.info(
                    "Dashboard stats for %s: total_sales=%s, invoice_count=%s",
                    today,
                    total_sales,
                    invoice_count_int,
                )

                return {
                    "total_sales": total_sales,
                    "invoice_count": invoice_count_int,
                }
        except Exception as e:
            logger.error("Error in get_today_dashboard_stats: %s", e, exc_info=True)
            raise