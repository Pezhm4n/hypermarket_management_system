from __future__ import annotations
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.models import Supplier

class SupplierController:
    def __init__(self, session_factory=None):
        self._session_factory = session_factory or SessionLocal

    def list_suppliers(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """لیست تأمین‌کنندگان را برای جدول نمایش می‌دهد"""
        with self._session_factory() as session:
            query = session.query(Supplier)
            if search:
                term = f"%{search.strip()}%"
                query = query.filter(
                    Supplier.CompanyName.ilike(term) | 
                    Supplier.ContactPerson.ilike(term) |
                    Supplier.Phone.ilike(term)
                )
            suppliers = query.order_by(Supplier.CompanyName).all()
            return [
                {
                    "sup_id": s.SupID,
                    "company_name": s.CompanyName,
                    "contact_person": s.ContactPerson,
                    "phone": s.Phone,
                    "email": s.Email,
                    "city": s.City,
                    "street": s.Street
                } for s in suppliers
            ]

    def create_supplier(self, name: str, phone: str, contact: str = "", email: str = "", city: str = "", street: str = ""):
        """افزودن تأمین‌کننده جدید"""
        with self._session_factory() as session:
            with session.begin():
                new_sup = Supplier(
                    CompanyName=name, Phone=phone, ContactPerson=contact,
                    Email=email, City=city, Street=street
                )
                session.add(new_sup)
                return True

    def update_supplier(self, sup_id: int, **kwargs):
        """ویرایش اطلاعات"""
        with self._session_factory() as session:
            with session.begin():
                sup = session.get(Supplier, sup_id)
                if sup:
                    for key, value in kwargs.items():
                        if hasattr(sup, key):
                            setattr(sup, key, value)
                    return True
                return False

    def delete_supplier(self, sup_id: int):
        """حذف تأمین‌کننده"""
        with self._session_factory() as session:
            with session.begin():
                sup = session.get(Supplier, sup_id)
                if sup:
                    session.delete(sup)
                    return True
                return False