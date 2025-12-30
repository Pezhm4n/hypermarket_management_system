from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

import logging
import re
import jdatetime
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import Category, InventoryBatch, Product

SessionFactory = Callable[[], Session]

logger = logging.getLogger(__name__)


class InventoryController:
    """
    Business logic for managing Product and InventoryBatch records.

    Provides CRUD operations used by the Inventory management UI.
    """

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory: SessionFactory = session_factory or SessionLocal

    def _get_session(self) -> Session:
        return self._session_factory()

    def _validate_barcode(self, barcode: str) -> str:
        """
        Validate barcode format: alphanumeric only.
        """
        barcode = barcode.strip()
        if not barcode:
            raise ValueError("Barcode is required.")
        if not re.fullmatch(r"[A-Za-z0-9]+", barcode):
            raise ValueError("Barcode must contain only numbers and English letters.")
        return barcode

    def _validate_price(self, price: Any, field_label: str) -> Decimal:
        """
        Validate and convert price to Decimal.
        """
        try:
            price_dec = Decimal(str(price))
            if price_dec < 0:
                raise ValueError(f"{field_label} cannot be negative.")
            return price_dec
        except Exception:
            raise ValueError(f"Invalid {field_label} value.")

    def _validate_quantity(self, quantity: Any, field_label: str) -> Decimal:
        """
        Validate and convert quantity to Decimal.
        """
        try:
            qty_dec = Decimal(str(quantity))
            if qty_dec < 0:
                raise ValueError(f"{field_label} cannot be negative.")
            return qty_dec
        except Exception:
            raise ValueError(f"Invalid {field_label} value.")

    # Category helpers
    def _get_or_create_category(self, session: Session, name: str) -> Category:
        """
        Get existing category by name or create a new one.
        """
        name = name.strip()
        if not name:
            raise ValueError("Category name must not be empty.")

        category = session.query(Category).filter(Category.Name == name).first()
        if category is not None:
            return category

        category = Category(Name=name)
        session.add(category)
        session.flush()
        return category

    def list_categories(self) -> List[str]:
        """
        Return all available category names sorted alphabetically.
        If no categories exist, create a default set.
        """
        with self._get_session() as session:
            with session.begin():
                categories = session.query(Category).order_by(Category.Name).all()
                
                if not categories:
                    default_categories = ["Food", "Beverage", "Snacks", "Dairy", "Other"]
                    for cat_name in default_categories:
                        session.add(Category(Name=cat_name))
                    session.flush()
                    categories = session.query(Category).order_by(Category.Name).all()

                return [cat.Name for cat in categories]

    # Product listing and lookup
    def list_products(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Return a list of products for display in the Inventory table.

        Each row contains:
            prod_id, name, barcode, category, base_price, total_stock, min_stock
        """
        with self._get_session() as session:
            query = (
                session.query(
                    Product.ProdID,
                    Product.Name,
                    Product.Barcode,
                    Category.Name.label("CategoryName"),
                    Product.BasePrice,
                    Product.MinStockLevel,
                    func.coalesce(
                        func.sum(InventoryBatch.CurrentQuantity),
                        0,
                    ).label("TotalStock"),
                )
                .join(Category, Product.CatID == Category.CatID)
                .outerjoin(InventoryBatch, InventoryBatch.ProdID == Product.ProdID)
                .group_by(
                    Product.ProdID,
                    Product.Name,
                    Product.Barcode,
                    Category.Name,
                    Product.BasePrice,
                    Product.MinStockLevel,
                )
            )

            if search:
                term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        Product.Name.ilike(term),
                        Product.Barcode.ilike(term),
                    )
                )

            rows = query.order_by(Product.Name).all()

            results: List[Dict[str, Any]] = []
            for row in rows:
                results.append(
                    {
                        "prod_id": row.ProdID,
                        "name": row.Name,
                        "barcode": row.Barcode,
                        "category": row.CategoryName,
                        "base_price": Decimal(str(row.BasePrice)) if row.BasePrice else Decimal("0"),
                        "total_stock": Decimal(str(row.TotalStock)),
                        "min_stock": row.MinStockLevel or 0,
                    }
                )

            return results

    def get_product(self, prod_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a single product with its category and total stock.
        """
        with self._get_session() as session:
            product: Optional[Product] = session.get(Product, prod_id)
            if product is None:
                return None

            category_name = product.category.Name if product.category else ""

            total_stock = (
                session.query(func.coalesce(func.sum(InventoryBatch.CurrentQuantity), 0))
                .filter(InventoryBatch.ProdID == prod_id)
                .scalar()
            )

            return {
                "prod_id": product.ProdID,
                "name": product.Name,
                "barcode": product.Barcode,
                "category": category_name,
                "base_price": Decimal(str(product.BasePrice)) if product.BasePrice else Decimal("0"),
                "min_stock": product.MinStockLevel or 0,
                "is_perishable": bool(product.IsPerishable),
                "total_stock": Decimal(str(total_stock)),
            }

    # CRUD operations
    def create_product(
        self,
        name: str,
        barcode: str,
        category_name: str,
        base_price: Any,
        min_stock: int,
        is_perishable: bool,
        initial_quantity: Any,
        buy_price: Any,
        expiry_date_jalali: Optional[str] = None,
    ) -> Product:
        """
        Create a new Product and an initial InventoryBatch in a single transaction.
        """
        name = name.strip()
        barcode = self._validate_barcode(barcode)
        category_name = category_name.strip()

        if not name:
            raise ValueError("Product name is required.")
        if not category_name:
            raise ValueError("Category is required.")

        base_price_dec = self._validate_price(base_price, "Base price")
        initial_qty_dec = self._validate_quantity(initial_quantity, "Initial quantity")
        buy_price_dec = self._validate_price(buy_price, "Purchase price")

        expiry_date_gregorian: Optional[date] = None
        if is_perishable:
            if not expiry_date_jalali:
                raise ValueError("INVALID_JALALI_DATE")
            try:
                parts = expiry_date_jalali.split("/")
                if len(parts) != 3:
                    raise ValueError("INVALID_JALALI_DATE")
                year, month, day = map(int, parts)
                j_date = jdatetime.date(year, month, day)
                expiry_date_gregorian = j_date.togregorian()
            except Exception as exc:
                raise ValueError("INVALID_JALALI_DATE") from exc

        with self._get_session() as session:
            with session.begin():
                existing_product = (
                    session.query(Product)
                    .filter(Product.Barcode == barcode)
                    .first()
                )
                if existing_product is not None:
                    raise ValueError("This barcode is already registered.")

                category = self._get_or_create_category(session, category_name)

                product = Product(
                    Name=name,
                    Barcode=barcode,
                    BasePrice=base_price_dec,
                    MinStockLevel=min_stock,
                    IsPerishable=is_perishable,
                    CatID=category.CatID,
                )
                session.add(product)
                session.flush()

                if initial_qty_dec > 0:
                    batch = InventoryBatch(
                        ProdID=product.ProdID,
                        OriginalQuantity=initial_qty_dec,
                        CurrentQuantity=initial_qty_dec,
                        BuyPrice=buy_price_dec,
                        ExpiryDate=expiry_date_gregorian,
                    )
                    session.add(batch)

                logger.info(
                    "Created product '%s' (Barcode=%s, ProdID=%s) with initial stock %.2f",
                    name,
                    barcode,
                    product.ProdID,
                    float(initial_qty_dec),
                )

                return product

    def update_product(
        self,
        prod_id: int,
        name: str,
        barcode: str,
        category_name: str,
        base_price: Any,
        min_stock: int,
        is_perishable: bool,
    ) -> None:
        """
        Update an existing Product's basic details.
        Note: This does not modify inventory batches.
        """
        name = name.strip()
        barcode = self._validate_barcode(barcode)
        category_name = category_name.strip()

        if not name:
            raise ValueError("Product name is required.")
        if not category_name:
            raise ValueError("Category is required.")

        base_price_dec = self._validate_price(base_price, "Base price")

        with self._get_session() as session:
            with session.begin():
                product: Optional[Product] = session.get(Product, prod_id)
                if product is None:
                    raise ValueError("Product not found.")

                existing_product = (
                    session.query(Product)
                    .filter(
                        Product.Barcode == barcode,
                        Product.ProdID != prod_id,
                    )
                    .first()
                )
                if existing_product is not None:
                    raise ValueError("This barcode is already used by another product.")

                category = self._get_or_create_category(session, category_name)

                product.Name = name
                product.Barcode = barcode
                product.BasePrice = base_price_dec
                product.MinStockLevel = min_stock
                product.IsPerishable = is_perishable
                product.CatID = category.CatID

                logger.info(
                    "Updated product '%s' (Barcode=%s, ProdID=%s)",
                    name,
                    barcode,
                    prod_id,
                )

    def delete_product(self, prod_id: int) -> None:
        """
        Delete a product and all related inventory batches.
        Note: This is a hard delete. Use with caution.
        """
        with self._get_session() as session:
            with session.begin():
                product: Optional[Product] = session.get(Product, prod_id)
                if product is None:
                    return

                session.query(InventoryBatch).filter(
                    InventoryBatch.ProdID == prod_id
                ).delete()

                session.delete(product)

                logger.info(
                    "Deleted product '%s' (Barcode=%s, ProdID=%s)",
                    product.Name,
                    product.Barcode,
                    prod_id,
                )