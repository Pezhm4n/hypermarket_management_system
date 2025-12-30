from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

# =====================================================
# 1. HR & SECURITY (RBAC)
# =====================================================


class Employee(Base):
    __tablename__ = "employee"

    EmpID = Column(Integer, primary_key=True, autoincrement=True)
    FirstName = Column(String, nullable=False)
    LastName = Column(String, nullable=False)
    Mobile = Column(String, nullable=False, unique=True)
    NationalID = Column(String, unique=True)
    HireDate = Column(DateTime)
    IsActive = Column(Boolean, server_default=text("true"))
    City = Column(String)
    Street = Column(String)
    ZipCode = Column(String)

    # Relationships
    user_account = relationship(
        "UserAccount",
        back_populates="employee",
        uselist=False,
    )
    purchase_orders = relationship(
        "PurchaseOrder",
        back_populates="employee",
    )
    shifts = relationship(
        "Shift",
        back_populates="employee",
    )


class UserAccount(Base):
    __tablename__ = "user_account"

    UserID = Column(Integer, primary_key=True, autoincrement=True)
    Username = Column(String, nullable=False, unique=True)
    PasswordHash = Column(String, nullable=False)
    LastLogin = Column(DateTime)
    IsLocked = Column(Boolean, server_default=text("false"))
    FailedLoginAttempts = Column(Integer, server_default=text("0"))
    LockoutUntil = Column(DateTime, nullable=True)
    CreatedAt = Column(DateTime, server_default=func.now())
    EmpID = Column(
        Integer,
        ForeignKey("employee.EmpID"),
        nullable=False,
        unique=True,
    )

    # Relationships
    employee = relationship(
        "Employee",
        back_populates="user_account",
    )
    user_roles = relationship(
        "UserRole",
        back_populates="user",
    )


class Role(Base):
    __tablename__ = "role"

    RoleID = Column(Integer, primary_key=True, autoincrement=True)
    Title = Column(String, nullable=False)  # Admin, Cashier, StoreKeeper
    Description = Column(String)

    # Relationships
    user_roles = relationship(
        "UserRole",
        back_populates="role",
    )


class UserRole(Base):
    __tablename__ = "user_role"

    UserRoleID = Column(Integer, primary_key=True, autoincrement=True)
    UserID = Column(Integer, ForeignKey("user_account.UserID"), nullable=False)
    RoleID = Column(Integer, ForeignKey("role.RoleID"), nullable=False)
    AssignedDate = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "UserID",
            "RoleID",
            name="uq_userrole_userid_roleid",
        ),
    )

    # Relationships
    user = relationship(
        "UserAccount",
        back_populates="user_roles",
    )
    role = relationship(
        "Role",
        back_populates="user_roles",
    )


# =====================================================
# 2. PRODUCT & SUPPLY CHAIN
# =====================================================


class Category(Base):
    __tablename__ = "category"

    CatID = Column(Integer, primary_key=True, autoincrement=True)
    Name = Column(String, nullable=False)
    ParentCatID = Column(
        Integer,
        ForeignKey("category.CatID"),
        nullable=True,
    )

    # Self-referential hierarchy
    parent = relationship(
        "Category",
        remote_side="Category.CatID",
        back_populates="children",
    )
    children = relationship(
        "Category",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    # Relationships
    products = relationship(
        "Product",
        back_populates="category",
    )


class Supplier(Base):
    __tablename__ = "supplier"

    SupID = Column(Integer, primary_key=True, autoincrement=True)
    CompanyName = Column(String, nullable=False)
    ContactPerson = Column(String)
    Phone = Column(String, nullable=False)
    Email = Column(String)
    City = Column(String)
    Street = Column(String)

    # Relationships
    product_suppliers = relationship(
        "ProductSupplier",
        back_populates="supplier",
    )
    inventory_batches = relationship(
        "InventoryBatch",
        back_populates="supplier",
    )
    purchase_orders = relationship(
        "PurchaseOrder",
        back_populates="supplier",
    )


class Product(Base):
    __tablename__ = "product"

    ProdID = Column(Integer, primary_key=True, autoincrement=True)
    Name = Column(String, nullable=False)
    Barcode = Column(String, nullable=False, unique=True)
    BasePrice = Column(Numeric(12, 2))
    MinStockLevel = Column(Integer)
    IsPerishable = Column(Boolean, server_default=text("false"))
    CatID = Column(
        Integer,
        ForeignKey("category.CatID"),
        nullable=False,
    )

    # Relationships
    category = relationship(
        "Category",
        back_populates="products",
    )
    product_suppliers = relationship(
        "ProductSupplier",
        back_populates="product",
    )
    inventory_batches = relationship(
        "InventoryBatch",
        back_populates="product",
    )
    purchase_order_items = relationship(
        "PurchaseOrderItem",
        back_populates="product",
    )
    invoice_items = relationship(
        "InvoiceItem",
        back_populates="product",
    )
    return_items = relationship(
        "ReturnItem",
        back_populates="product",
    )


class ProductSupplier(Base):
    __tablename__ = "product_supplier"

    PS_ID = Column(Integer, primary_key=True, autoincrement=True)
    ProdID = Column(Integer, ForeignKey("product.ProdID"), nullable=False)
    SupID = Column(Integer, ForeignKey("supplier.SupID"), nullable=False)
    WholesalePrice = Column(Numeric(12, 2))
    LeadTimeDays = Column(Integer)
    IsPrimary = Column(Boolean, server_default=text("false"))

    __table_args__ = (
        UniqueConstraint(
            "ProdID",
            "SupID",
            name="uq_productsupplier_prodid_supid",
        ),
    )

    # Relationships
    product = relationship(
        "Product",
        back_populates="product_suppliers",
    )
    supplier = relationship(
        "Supplier",
        back_populates="product_suppliers",
    )


# =====================================================
# 3. INVENTORY (BATCH-BASED – FEFO/FIFO)
# =====================================================


class InventoryBatch(Base):
    __tablename__ = "inventory_batch"

    BatchID = Column(Integer, primary_key=True, autoincrement=True)
    ProdID = Column(Integer, ForeignKey("product.ProdID"), nullable=False)
    SupID = Column(Integer, ForeignKey("supplier.SupID"), nullable=True)
    BatchNumber = Column(String)
    OriginalQuantity = Column(Numeric(12, 3), nullable=False)
    CurrentQuantity = Column(Numeric(12, 3), nullable=False)
    BuyPrice = Column(Numeric(12, 2))
    EntryDate = Column(DateTime, server_default=func.now())
    ExpiryDate = Column(Date, nullable=True)
    LocationCode = Column(String)

    __table_args__ = (
        Index("ix_inventorybatch_prodid", "ProdID"),
        Index("ix_inventorybatch_expirydate", "ExpiryDate"),
    )

    # Relationships
    product = relationship(
        "Product",
        back_populates="inventory_batches",
    )
    supplier = relationship(
        "Supplier",
        back_populates="inventory_batches",
    )
    invoice_items = relationship(
        "InvoiceItem",
        back_populates="batch",
    )


# =====================================================
# 4. PROCUREMENT (PURCHASE ORDERS)
# =====================================================


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"

    PO_ID = Column(Integer, primary_key=True, autoincrement=True)
    SupID = Column(Integer, ForeignKey("supplier.SupID"), nullable=False)
    EmpID = Column(Integer, ForeignKey("employee.EmpID"), nullable=False)
    OrderDate = Column(DateTime, server_default=func.now())
    Status = Column(String)  # Pending, Received, Cancelled
    TotalCost = Column(Numeric(12, 2))

    # Relationships
    supplier = relationship(
        "Supplier",
        back_populates="purchase_orders",
    )
    employee = relationship(
        "Employee",
        back_populates="purchase_orders",
    )
    items = relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_item"

    ItemID = Column(Integer, primary_key=True, autoincrement=True)
    PO_ID = Column(Integer, ForeignKey("purchase_order.PO_ID"), nullable=False)
    ProdID = Column(Integer, ForeignKey("product.ProdID"), nullable=False)
    Quantity = Column(Integer, nullable=False)
    UnitCost = Column(Numeric(12, 2))

    __table_args__ = (
        UniqueConstraint(
            "PO_ID",
            "ProdID",
            name="uq_purchaseorderitem_poid_prodid",
        ),
    )

    # Relationships
    purchase_order = relationship(
        "PurchaseOrder",
        back_populates="items",
    )
    product = relationship(
        "Product",
        back_populates="purchase_order_items",
    )


# =====================================================
# 5. SALES & SHIFT MANAGEMENT
# =====================================================


class Shift(Base):
    __tablename__ = "shift"

    ShiftID = Column(Integer, primary_key=True, autoincrement=True)
    EmpID = Column(Integer, ForeignKey("employee.EmpID"), nullable=False)
    StartTime = Column(DateTime, server_default=func.now())
    EndTime = Column(DateTime, nullable=True)
    StartCash = Column(Numeric(12, 2))
    EndCash = Column(Numeric(12, 2))
    SystemCalculatedCash = Column(Numeric(12, 2))
    CashFloat = Column(Numeric(12, 2))
    Status = Column(String)  # Open, Closed

    # Relationships
    employee = relationship(
        "Employee",
        back_populates="shifts",
    )
    invoices = relationship(
        "Invoice",
        back_populates="shift",
    )


class Customer(Base):
    __tablename__ = "customer"

    CustID = Column(Integer, primary_key=True, autoincrement=True)
    FullName = Column(String)
    Phone = Column(String, unique=True)
    RegDate = Column(DateTime)
    LoyaltyPoints = Column(Integer, server_default=text("0"))

    # Relationships
    invoices = relationship(
        "Invoice",
        back_populates="customer",
    )


class Invoice(Base):
    __tablename__ = "invoice"

    InvID = Column(Integer, primary_key=True, autoincrement=True)
    ShiftID = Column(Integer, ForeignKey("shift.ShiftID"), nullable=False)
    CustID = Column(Integer, ForeignKey("customer.CustID"), nullable=True)
    Date = Column(DateTime, server_default=func.now())
    TotalAmount = Column(Numeric(12, 2))
    Status = Column(String)  # Draft, Completed, Void

    __table_args__ = (
        Index("ix_invoice_date", "Date"),
    )

    # Relationships
    shift = relationship(
        "Shift",
        back_populates="invoices",
    )
    customer = relationship(
        "Customer",
        back_populates="invoices",
    )
    items = relationship(
        "InvoiceItem",
        back_populates="invoice",
    )
    payments = relationship(
        "Payment",
        back_populates="invoice",
    )
    returns = relationship(
        "Returns",
        back_populates="original_invoice",
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_item"

    ItemID = Column(Integer, primary_key=True, autoincrement=True)
    InvID = Column(Integer, ForeignKey("invoice.InvID"), nullable=False)
    ProdID = Column(Integer, ForeignKey("product.ProdID"), nullable=False)
    BatchID = Column(Integer, ForeignKey("inventory_batch.BatchID"), nullable=True)
    Quantity = Column(Numeric(12, 3), nullable=False)
    UnitPrice = Column(Numeric(12, 2), nullable=False)
    Discount = Column(Numeric(12, 2), server_default=text("0"))
    TaxAmount = Column(Numeric(12, 2), server_default=text("0"))
    LineTotal = Column(Numeric(12, 2), nullable=False)

    __table_args__ = (
        Index("ix_invoiceitem_invid", "InvID"),
        Index("ix_invoiceitem_prodid", "ProdID"),
    )

    # Relationships
    invoice = relationship(
        "Invoice",
        back_populates="items",
    )
    product = relationship(
        "Product",
        back_populates="invoice_items",
    )
    batch = relationship(
        "InventoryBatch",
        back_populates="invoice_items",
    )
    return_items = relationship(
        "ReturnItem",
        back_populates="invoice_item",
    )


class Payment(Base):
    __tablename__ = "payment"

    PayID = Column(Integer, primary_key=True, autoincrement=True)
    InvID = Column(Integer, ForeignKey("invoice.InvID"), nullable=False)
    Amount = Column(Numeric(12, 2), nullable=False)
    Method = Column(String, nullable=False)  # Cash, Card, Online
    PayDate = Column(DateTime, server_default=func.now())
    TransactionRef = Column(String)

    # Relationships
    invoice = relationship(
        "Invoice",
        back_populates="payments",
    )


# =====================================================
# 6. RETURNS (AFTER-SALES SUPPORT)
# =====================================================


class Returns(Base):
    __tablename__ = "returns"

    ReturnID = Column(Integer, primary_key=True, autoincrement=True)
    OriginalInvID = Column(Integer, ForeignKey("invoice.InvID"), nullable=False)
    ReturnDate = Column(DateTime, server_default=func.now())
    Reason = Column(String)
    RefundAmount = Column(Numeric(12, 2))

    # Relationships
    original_invoice = relationship(
        "Invoice",
        back_populates="returns",
    )
    items = relationship(
        "ReturnItem",
        back_populates="returns",
    )


class ReturnItem(Base):
    __tablename__ = "return_item"

    ReturnItemID = Column(Integer, primary_key=True, autoincrement=True)
    ReturnID = Column(Integer, ForeignKey("returns.ReturnID"), nullable=False)
    ItemID = Column(Integer, ForeignKey("invoice_item.ItemID"), nullable=True)
    ProdID = Column(Integer, ForeignKey("product.ProdID"), nullable=False)
    Quantity = Column(Numeric(12, 3))
    RefundLineAmount = Column(Numeric(12, 2))

    # Relationships
    returns = relationship(
        "Returns",
        back_populates="items",
    )
    invoice_item = relationship(
        "InvoiceItem",
        back_populates="return_items",
    )
    product = relationship(
        "Product",
        back_populates="return_items",
    )