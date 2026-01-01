from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Tuple

import json
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import (
    LOYALTY_EARN_RATE,
    LOYALTY_EARN_THRESHOLD,
    LOYALTY_POINT_VALUE,
)
from app.database import SessionLocal
from app.models.models import (
    Customer,
    InventoryBatch,
    Invoice,
    InvoiceItem,
    ParkedOrder,
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
    # Parked orders (hold / recall)
    # --------------------------------------------------------------------- #
    def park_order(
        self,
        cart_items: Iterable[Mapping[str, Any]],
        cust_id: Optional[int],
    ) -> int:
        """
        Persist the current cart as a parked order and return the ParkID.
        """
        try:
            items_list: list[dict] = [dict(item) for item in cart_items]
            if not items_list:
                raise ValueError("Cannot park an empty cart.")

            payload = json.dumps(items_list, ensure_ascii=False, default=str)

            with self._get_session() as session:
                with session.begin():
                    parked = ParkedOrder(
                        CustID=cust_id,
                        CartData=payload,
                    )
                    session.add(parked)
                    session.flush()
                    park_id = parked.ParkID

            logger.info(
                "Parked order created successfully: ParkID=%s, CustID=%s, items=%d",
                park_id,
                cust_id,
                len(items_list),
            )
            return int(park_id)
        except Exception as e:
            logger.error("Error in park_order: %s", e, exc_info=True)
            raise

    def get_parked_orders(self) -> list[dict]:
        """
        Return a list of parked orders with basic metadata.
        """
        try:
            results: list[dict] = []
            with self._get_session() as session:
                rows: Sequence[tuple[ParkedOrder, Optional[Customer]]] = (
                    session.query(ParkedOrder, Customer)
                    .outerjoin(Customer, ParkedOrder.CustID == Customer.CustID)
                    .order_by(ParkedOrder.CreatedAt.desc())
                    .all()
                )

                for parked, customer in rows:
                    try:
                        items = json.loads(parked.CartData or "[]")
                    except Exception:
                        items = []
                    total = self.calculate_cart_total(items)
                    cust_name = None
                    if customer is not None:
                        cust_name = customer.FullName or customer.Phone or None

                    results.append(
                        {
                            "park_id": parked.ParkID,
                            "created_at": parked.CreatedAt,
                            "customer_id": parked.CustID,
                            "customer_name": cust_name,
                            "total": total,
                        }
                    )
            return results
        except Exception as e:
            logger.error("Error in get_parked_orders: %s", e, exc_info=True)
            raise

    def restore_order(self, park_id: int) -> dict:
        """
        Load and delete a parked order, returning its cart and customer info.
        """
        try:
            with self._get_session() as session:
                with session.begin():
                    parked: Optional[ParkedOrder] = session.get(ParkedOrder, park_id)
                    if parked is None:
                        raise ValueError("Parked order not found.")

                    try:
                        items = json.loads(parked.CartData or "[]")
                    except Exception as exc:
                        raise ValueError("Parked cart data is corrupted.") from exc

                    customer: Optional[Customer] = None
                    if parked.CustID is not None:
                        customer = session.get(Customer, parked.CustID)

                    cust_name = None
                    if customer is not None:
                        cust_name = customer.FullName or customer.Phone or None

                    result = {
                        "park_id": parked.ParkID,
                        "customer_id": parked.CustID,
                        "customer_name": cust_name,
                        "items": items,
                    }

                    session.delete(parked)

            logger.info("Restored parked order ParkID=%s", park_id)
            return result
        except Exception as e:
            logger.error("Error in restore_order: %s", e, exc_info=True)
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
                "cash_float": Decimal,
                "final_balance": Decimal,
                "start_cash": Decimal,
                "start_time": datetime | None,
                "end_time": datetime | None,
                "employee_name": str | None,
                "items": list[dict],
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
                    cash_float = (
                        Decimal(str(shift.CashFloat))
                        if getattr(shift, "CashFloat", None) is not None
                        else Decimal("0")
                    )

                    final_balance = (start_cash + total_sales).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )

                    shift.SystemCalculatedCash = final_balance
                    closed_at = datetime.utcnow()
                    shift.EndTime = closed_at
                    shift.Status = "Closed"

                    # Aggregate sold items for this shift grouped by product
                    item_rows = (
                        session.query(
                            Product.Name,
                            func.coalesce(
                                func.sum(InvoiceItem.Quantity),
                                0,
                            ).label("qty"),
                            func.coalesce(
                                func.sum(InvoiceItem.LineTotal),
                                0,
                            ).label("total"),
                        )
                        .join(
                            InvoiceItem,
                            InvoiceItem.ProdID == Product.ProdID,
                        )
                        .join(
                            Invoice,
                            Invoice.InvID == InvoiceItem.InvID,
                        )
                        .filter(
                            Invoice.ShiftID == shift_id,
                            Invoice.Status != "Void",
                        )
                        .group_by(Product.Name)
                        .order_by(Product.Name.asc())
                        .all()
                    )

                    items: list[dict] = []
                    for name, qty_raw, total_raw in item_rows:
                        qty_dec = Decimal(str(qty_raw or 0)).quantize(
                            Decimal("0.01"),
                            rounding=ROUND_HALF_UP,
                        )
                        total_dec = Decimal(str(total_raw or 0)).quantize(
                            Decimal("0.01"),
                            rounding=ROUND_HALF_UP,
                        )
                        items.append(
                            {
                                "name": name,
                                "quantity": qty_dec,
                                "total": total_dec,
                            }
                        )

                    employee_name: str | None = None
                    if getattr(shift, "employee", None) is not None:
                        first = getattr(shift.employee, "FirstName", "") or ""
                        last = getattr(shift.employee, "LastName", "") or ""
                        full_name = f"{first} {last}".strip()
                        employee_name = full_name or None

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
                        "cash_float": cash_float,
                        "final_balance": final_balance,
                        "start_cash": start_cash,
                        "start_time": shift.StartTime,
                        "end_time": shift.EndTime,
                        "employee_name": employee_name,
                        "items": items,
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
        cust_id: Optional[int] = None,
        is_refund: bool = False,
        discount_amount: Any = 0,
        loyalty_points_to_use: Optional[int] = None,
    ) -> bool:
        """
        Perform a complete checkout operation in a single DB transaction.

        Steps:
            * Validate input and recompute cart total.
            * Apply discount to compute final total.
            * Create Invoice (Status='Paid' or 'Refund').
            * Deduct or add inventory depending on transaction type.
            * Create InvoiceItem rows per product/batch.
            * Create a Payment row linked to the Invoice.
            * Update customer loyalty points for accrual/redemption.

        Raises ValueError for business-rule violations (e.g. insufficient stock
        or missing shift). Any exception aborts the transaction.
        """
        try:
            cart_items_list = list(cart_items)
            if not cart_items_list:
                raise ValueError("Cart is empty.")

            logger.info(
                "Starting checkout: shift_id=%s, items=%d, payment_method=%s, is_refund=%s, discount=%s, loyalty_points=%s",
                shift_id,
                len(cart_items_list),
                payment_method,
                is_refund,
                discount_amount,
                loyalty_points_to_use,
            )

            # Subtotal from cart
            subtotal = self.calculate_cart_total(cart_items_list)
            if is_refund and subtotal > 0:
                subtotal = -subtotal

            try:
                discount_dec = Decimal(str(discount_amount or 0)).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            except Exception:
                discount_dec = Decimal("0.00")

            if discount_dec < 0:
                discount_dec = Decimal("0.00")

            final_total = (subtotal - discount_dec).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            if is_refund and final_total > 0:
                final_total = -final_total

            # Normalize requested loyalty points
            try:
                loyalty_points_int = int(loyalty_points_to_use or 0)
            except Exception:
                loyalty_points_int = 0
            if loyalty_points_int < 0:
                loyalty_points_int = 0

            # total_amount is accepted but not trusted blindly; we base persistence
            # on the calculated final total.
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

                    customer: Optional[Customer] = None
                    if cust_id is not None:
                        customer = session.get(Customer, cust_id)

                    # Create invoice
                    invoice = Invoice(
                        ShiftID=shift_id,
                        CustID=cust_id,
                        TotalAmount=final_total,
                        Discount=discount_dec,
                        Status="Refund" if is_refund else "Paid",
                    )
                    session.add(invoice)
                    session.flush()  # Ensure InvID is available

                    # Process each cart line
                    for item in cart_items_list:
                        prod_id = int(item["ProdID"])
                        qty = Decimal(str(item["Quantity"]))
                        unit_price = Decimal(str(item["UnitPrice"]))

                        if qty == 0:
                            logger.info(
                                "Skipping cart line with zero quantity: ProdID=%s",
                                prod_id,
                            )
                            continue

                        if not is_refund:
                            if qty < 0:
                                raise ValueError(
                                    f"Negative quantity is not allowed for normal sale. ProdID={prod_id}, Qty={qty}"
                                )

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
                        else:
                            # Refund: increase stock by the absolute quantity and create negative invoice items.
                            qty_abs = abs(qty)
                            if qty_abs <= 0:
                                continue

                            # Create a new batch representing returned goods.
                            batch = InventoryBatch(
                                ProdID=prod_id,
                                OriginalQuantity=qty_abs,
                                CurrentQuantity=qty_abs,
                                BuyPrice=unit_price,
                                EntryDate=datetime.utcnow(),
                            )
                            session.add(batch)
                            session.flush()

                            refund_qty = -qty_abs
                            line_total = (refund_qty * unit_price).quantize(
                                Decimal("0.01"),
                                rounding=ROUND_HALF_UP,
                            )

                            invoice_item = InvoiceItem(
                                InvID=invoice.InvID,
                                ProdID=prod_id,
                                BatchID=batch.BatchID,
                                Quantity=refund_qty,
                                UnitPrice=unit_price,
                                Discount=Decimal("0"),
                                TaxAmount=Decimal("0"),
                                LineTotal=line_total,
                            )
                            session.add(invoice_item)

                    # Record payment (negative for refunds)
                    payment = Payment(
                        InvID=invoice.InvID,
                        Amount=final_total,
                        Method=payment_method,
                        TransactionRef=None,
                    )
                    session.add(payment)

                    # Loyalty: redemption and accrual for normal sales with a known customer
                    if not is_refund and customer is not None:
                        try:
                            existing_points = int(customer.LoyaltyPoints or 0)
                        except Exception:
                            existing_points = 0
                        if existing_points < 0:
                            existing_points = 0

                        points_spent = 0
                        points_earned = 0

                        if loyalty_points_int > 0:
                            if loyalty_points_int > existing_points:
                                raise ValueError(
                                    "Customer does not have enough loyalty points."
                                )
                            points_spent = loyalty_points_int

                        # Net total used for accrual is the final amount paid (non-negative)
                        net_total = final_total
                        if net_total < 0:
                            net_total = Decimal("0")

                        if net_total > 0 and LOYALTY_EARN_THRESHOLD > 0:
                            threshold = Decimal(str(LOYALTY_EARN_THRESHOLD))
                            try:
                                blocks = int(net_total // threshold)
                            except Exception:
                                blocks = 0
                            if blocks > 0 and LOYALTY_EARN_RATE > 0:
                                points_earned = blocks * LOYALTY_EARN_RATE

                        new_balance = existing_points - points_spent + points_earned
                        if new_balance < 0:
                            new_balance = 0

                        customer.LoyaltyPoints = new_balance

                        if points_spent > 0:
                            logger.info(
                                "Customer %s spent %s loyalty point(s). New balance=%s",
                                cust_id,
                                points_spent,
                                new_balance,
                            )
                        if points_earned > 0:
                            logger.info(
                                "Customer %s earned %s loyalty point(s) on net_total=%s. New balance=%s",
                                cust_id,
                                points_earned,
                                net_total,
                                new_balance,
                            )

            logger.info(
                "Checkout completed successfully for shift_id=%s, total=%s, discount=%s",
                shift_id,
                final_total,
                discount_dec,
            )
            # If we reach here without exception, the transaction was committed.
            return True
        except Exception as e:
            logger.error("Error in process_checkout: %s", e, exc_info=True)
            raise

    def get_customer_loyalty_points(self, cust_id: Optional[int]) -> int:
        """
        Return the current loyalty points balance for the given customer.
        """
        try:
            if cust_id is None:
                return 0

            with self._get_session() as session:
                customer = session.get(Customer, cust_id)
                if customer is None:
                    return 0
                try:
                    points = int(customer.LoyaltyPoints or 0)
                except Exception:
                    points = 0
                return max(points, 0)
        except Exception as e:
            logger.error(
                "Error in get_customer_loyalty_points for CustID=%s: %s",
                cust_id,
                e,
                exc_info=True,
            )
            raise

    def calculate_max_redeemable_discount(
        self,
        cust_id: Optional[int],
        invoice_total: Any,
    ) -> Tuple[int, Decimal]:
        """
        Calculate how many loyalty points can be redeemed for a given invoice
        total and the corresponding monetary discount.

        Returns (max_points_to_use, discount_amount).
        """
        try:
            if cust_id is None:
                return 0, Decimal("0")

            try:
                total_dec = Decimal(str(invoice_total or 0)).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            except Exception:
                total_dec = Decimal("0.00")

            if total_dec <= 0:
                return 0, Decimal("0")

            with self._get_session() as session:
                customer = session.get(Customer, cust_id)
                if customer is None:
                    return 0, Decimal("0")

                try:
                    current_points = int(customer.LoyaltyPoints or 0)
                except Exception:
                    current_points = 0
                if current_points <= 0:
                    return 0, Decimal("0")

                point_value = Decimal(str(LOYALTY_POINT_VALUE))
                max_discount_by_points = point_value * Decimal(current_points)

                effective_discount = min(max_discount_by_points, total_dec)
                if effective_discount <= 0:
                    return 0, Decimal("0")

                max_points_by_amount = int(effective_discount // point_value)
                if max_points_by_amount <= 0:
                    return 0, Decimal("0")

                discount_amount = point_value * Decimal(max_points_by_amount)
                return max_points_by_amount, discount_amount.quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
        except Exception as e:
            logger.error(
                "Error in calculate_max_redeemable_discount for CustID=%s: %s",
                cust_id,
                e,
                exc_info=True,
            )
            raise

    def apply_loyalty_discount(
        self,
        invoice_id: int,
        points_to_use: int,
    ) -> Decimal:
        """
        Apply a loyalty discount to an existing invoice and deduct points from
        the associated customer.

        Returns the discount amount applied (in currency units).
        """
        try:
            if points_to_use <= 0:
                return Decimal("0")

            with self._get_session() as session:
                with session.begin():
                    invoice = session.get(Invoice, invoice_id)
                    if invoice is None:
                        raise ValueError("Invoice not found.")

                    if invoice.Status == "Void":
                        raise ValueError("Cannot apply loyalty discount to a void invoice.")

                    if invoice.CustID is None:
                        raise ValueError(
                            "Cannot apply loyalty discount to an invoice without a customer."
                        )

                    customer = session.get(Customer, invoice.CustID)
                    if customer is None:
                        raise ValueError("Customer not found for invoice.")

                    try:
                        current_points = int(customer.LoyaltyPoints or 0)
                    except Exception:
                        current_points = 0
                    if current_points < 0:
                        current_points = 0

                    if points_to_use > current_points:
                        raise ValueError("Customer does not have enough loyalty points.")

                    point_value = Decimal(str(LOYALTY_POINT_VALUE))
                    requested_discount = point_value * Decimal(points_to_use)

                    try:
                        invoice_total = Decimal(str(invoice.TotalAmount or 0))
                    except Exception:
                        invoice_total = Decimal("0.00")

                    if invoice_total <= 0:
                        return Decimal("0")

                    max_discount = invoice_total
                    if requested_discount > max_discount:
                        requested_discount = max_discount
                        points_to_use = int(requested_discount // point_value)

                    if points_to_use <= 0 or requested_discount <= 0:
                        return Decimal("0")

                    # Apply discount and update invoice totals
                    invoice.Discount = requested_discount.quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                    invoice.TotalAmount = (invoice_total - requested_discount).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )

                    # Deduct points
                    new_balance = current_points - points_to_use
                    if new_balance < 0:
                        new_balance = 0
                    customer.LoyaltyPoints = new_balance

                    logger.info(
                        "Applied loyalty discount on InvoiceID=%s: points_used=%s, discount=%s, new_balance=%s",
                        invoice_id,
                        points_to_use,
                        requested_discount,
                        new_balance,
                    )

                    return requested_discount.quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
        except Exception as e:
            logger.error("Error in apply_loyalty_discount: %s", e, exc_info=True)
            raise

    # --------------------------------------------------------------------- #
    # Dashboard helpers
    # --------------------------------------------------------------------- #
    def get_dashboard_stats(self) -> dict:
        """
        Return today's dashboard KPIs as a dictionary:

            {
                "total_sales": Decimal,        # Sum of today's non-void invoice totals
                "transaction_count": int,      # Count of today's non-void invoices
                "total_profit": Decimal,       # Sum((UnitPrice - BuyPrice) * Quantity)
                "low_stock_count": int,        # Count of products below MinStockLevel
            }
        """
        try:
            today = date.today()
            # Use explicit datetime range [today 00:00, tomorrow 00:00)
            start_dt = datetime.combine(today, datetime.min.time())
            end_dt = start_dt + timedelta(days=1)
            logger.info("Calculating dashboard stats for %s.", today)

            with self._get_session() as session:
                # ------------------------------------------------------------------
                # Total sales and transaction count
                # ------------------------------------------------------------------
                total_sales_raw, invoice_count = (
                    session.query(
                        func.coalesce(func.sum(Invoice.TotalAmount), 0),
                        func.count(Invoice.InvID),
                    )
                    .filter(
                        Invoice.Date >= start_dt,
                        Invoice.Date < end_dt,
                        Invoice.Status != "Void",
                    )
                    .one()
                )

                total_sales = Decimal(str(total_sales_raw or 0)).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
                transaction_count = int(invoice_count or 0)

                # ------------------------------------------------------------------
                # Total profit for today:
                # Sum((InvoiceItem.UnitPrice - InventoryBatch.BuyPrice) * Quantity)
                # Batch cost falls back to Product.BasePrice, then 0 if both missing.
                # ------------------------------------------------------------------
                cost_expr = func.coalesce(
                    InventoryBatch.BuyPrice,
                    Product.BasePrice,
                    0,
                )
                profit_expr = (InvoiceItem.UnitPrice - cost_expr) * InvoiceItem.Quantity

                total_profit_raw = (
                    session.query(
                        func.coalesce(func.sum(profit_expr), 0),
                    )
                    .select_from(Invoice)
                    .join(InvoiceItem, InvoiceItem.InvID == Invoice.InvID)
                    .outerjoin(
                        InventoryBatch,
                        InvoiceItem.BatchID == InventoryBatch.BatchID,
                    )
                    .outerjoin(
                        Product,
                        InvoiceItem.ProdID == Product.ProdID,
                    )
                    .filter(
                        Invoice.Date >= start_dt,
                        Invoice.Date < end_dt,
                        Invoice.Status != "Void",
                    )
                    .scalar()
                )

                total_profit = Decimal(str(total_profit_raw or 0)).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

                # ------------------------------------------------------------------
                # Low stock products: distinct active products where
                # Total(CurrentQuantity) <= MinStockLevel and MinStockLevel > 0.
                # ------------------------------------------------------------------
                stock_subq = (
                    session.query(
                        Product.ProdID.label("ProdID"),
                        func.coalesce(
                            func.sum(InventoryBatch.CurrentQuantity),
                            0,
                        ).label("TotalQty"),
                        Product.MinStockLevel.label("MinStock"),
                        Product.IsActive.label("IsActive"),
                    )
                    .outerjoin(
                        InventoryBatch,
                        InventoryBatch.ProdID == Product.ProdID,
                    )
                    .group_by(
                        Product.ProdID,
                        Product.MinStockLevel,
                        Product.IsActive,
                    )
                ).subquery("stock")

                low_stock_count_raw = (
                    session.query(func.count())
                    .select_from(stock_subq)
                    .filter(
                        stock_subq.c.IsActive == True,  # noqa: E712
                        func.coalesce(stock_subq.c.MinStock, 0) > 0,
                        stock_subq.c.TotalQty <= stock_subq.c.MinStock,
                    )
                    .scalar()
                )

                low_stock_count = int(low_stock_count_raw or 0)

                logger.info(
                    (
                        "Dashboard stats for %s: total_sales=%s, "
                        "transactions=%s, profit=%s, low_stock_count=%s"
                    ),
                    today,
                    total_sales,
                    transaction_count,
                    total_profit,
                    low_stock_count,
                )

                return {
                    "total_sales": total_sales,
                    "transaction_count": transaction_count,
                    "total_profit": total_profit,
                    "low_stock_count": low_stock_count,
                }
        except Exception as e:
            logger.error("Error in get_dashboard_stats: %s", e, exc_info=True)
            raise

    def get_today_dashboard_stats(self) -> dict:
        """
        Backwards-compatible wrapper that returns today's total sales amount
        and invoice count only.
        """
        try:
            stats = self.get_dashboard_stats()
            return {
                "total_sales": stats.get("total_sales", Decimal("0")),
                "invoice_count": int(stats.get("transaction_count") or 0),
            }
        except Exception as e:
            logger.error("Error in get_today_dashboard_stats: %s", e, exc_info=True)
            raise

    def get_last_7_days_sales_series(self) -> dict:
        """
        Return per-day sales totals for the last 7 days (including today).

        Returns
        -------
        dict
            {
                "labels": [str],   # ISO-formatted dates YYYY-MM-DD
                "totals": [Decimal],
            }
        """
        try:
            today = date.today()
            start_date = today - timedelta(days=6)
            logger.info(
                "Calculating 7-day sales series from %s to %s.",
                start_date,
                today,
            )

            with self._get_session() as session:
                rows = (
                    session.query(
                        func.date(Invoice.Date).label("day"),
                        func.coalesce(func.sum(Invoice.TotalAmount), 0).label("total"),
                    )
                    .filter(
                        Invoice.Date >= start_date,
                        Invoice.Status != "Void",
                    )
                    .group_by("day")
                    .order_by("day")
                    .all()
                )

                totals_by_day: dict[date, Decimal] = {}
                for day_raw, total_raw in rows:
                    day_value = day_raw
                    total_dec = Decimal(str(total_raw or 0)).quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                    totals_by_day[day_value] = total_dec

                labels: list[str] = []
                totals: list[Decimal] = []

                for offset in range(6, -1, -1):
                    day_value = today - timedelta(days=offset)
                    labels.append(day_value.strftime("%Y-%m-%d"))
                    totals.append(totals_by_day.get(day_value, Decimal("0")))

                logger.info(
                    "7-day sales series prepared: %s",
                    list(zip(labels, totals)),
                )
                return {
                    "labels": labels,
                    "totals": totals,
                }
        except Exception as e:
            logger.error(
                "Error in get_last_7_days_sales_series: %s",
                e,
                exc_info=True,
            )
            raise