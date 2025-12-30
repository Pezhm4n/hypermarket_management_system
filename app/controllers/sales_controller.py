from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import InventoryBatch, Product

SessionFactory = Callable[[], Session]


class SalesController:
    """
    Business logic for the Sales / POS module.

    This is a scaffold intended for further expansion (discounts, taxes,
    promotions, etc.) while already providing basic product lookup and cart
    total calculation.
    """

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory: SessionFactory = session_factory or SessionLocal

    def _get_session(self) -> Session:
        return self._session_factory()

    def get_product_by_barcode(
        self,
        barcode: str,
    ) -> Optional[tuple[Product, Decimal]]:
        """
        Look up a product by its barcode, together with aggregated stock.

        Returns:
            (Product, stock_quantity) if found, otherwise None.

        stock_quantity is the sum of all InventoryBatch.CurrentQuantity for the
        given product, or Decimal(0) if there are no batches.
        """
        if not barcode:
            return None

        with self._get_session() as session:
            result = (
                session.query(
                    Product,
                    func.coalesce(
                        func.sum(InventoryBatch.CurrentQuantity),
                        0,
                    ).label("stock_quantity"),
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

            product, stock_quantity = result
            return product, Decimal(stock_quantity)

    def calculate_cart_total(
        self,
        cart_items: Iterable[Mapping[str, Any]],
    ) -> Decimal:
        """
        Calculate the total amount for a collection of cart items.

        Each cart item is expected to be a mapping with at least:
            - 'quantity'
            - 'unit_price'

        Values are converted to Decimal for accurate financial calculations.
        """
        total = Decimal("0")
        for item in cart_items:
            qty = Decimal(str(item.get("quantity", 0)))
            price = Decimal(str(item.get("unit_price", 0)))
            total += qty * price

        return total