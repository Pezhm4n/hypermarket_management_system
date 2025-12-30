from __future__ import annotations

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


class SalesController:
    """
    Business logic for the Sales / POS module.

    Provides product lookup, cart total calculation and transactional checkout
    with FIFO (expiry-date based) inventory deduction.
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
        if not barcode:
            return None

        with self._get_session() as session:
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
                .filter(Product.Barcode == barcode)
                .group_by(Product.ProdID)
                .first()
            )

            if result is None:
                return None

            prod_id, name, barcode_val, base_price, total_stock = result

            base_price_dec = (
                Decimal(str(base_price)) if base_price is not None else Decimal("0")
            )
            total_stock_dec = Decimal(str(total_stock))

            return {
                "ProdID": prod_id,
                "Name": name,
                "Barcode": barcode_val,
                "BasePrice": base_price_dec,
                "TotalStock": total_stock_dec,
            }

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
        total = Decimal("0")
        for item in cart_items:
            qty = Decimal(str(item.get("Quantity", 0)))
            price = Decimal(str(item.get("UnitPrice", 0)))
            total += qty * price

        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # --------------------------------------------------------------------- #
    # Shift helpers
    # --------------------------------------------------------------------- #
    def get_or_create_active_shift(self, emp_id: Optional[int]) -> int:
        """
        Return an open shift for the given employee, creating one if needed.

        This is a pragmatic helper for Phase 4 – in a fuller implementation,
        explicit shift open/close flows would manage this instead.
        """
        if emp_id is None:
            raise ValueError("Current employee could not be determined.")

        with self._get_session() as session:
            shift = (
                session.query(Shift)
                .filter(Shift.EmpID == emp_id, Shift.Status == "Open")
                .order_by(Shift.StartTime.desc())
                .first()
            )

            if shift is not None:
                return shift.ShiftID

            shift = Shift(
                EmpID=emp_id,
                Status="Open",
            )
            session.add(shift)
            session.commit()
            session.refresh(shift)
            return shift.ShiftID

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
        cart_items = list(cart_items)
        if not cart_items:
            raise ValueError("Cart is empty.")

        computed_total = self.calculate_cart_total(cart_items)

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
                for item in cart_items:
                    prod_id = int(item["ProdID"])
                    qty = Decimal(str(item["Quantity"]))
                    unit_price = Decimal(str(item["UnitPrice"]))

                    if qty <= 0:
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

            # If we reach here without exception, the transaction was committed.
            return True