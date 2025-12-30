from __future__ import annotations

from datetime import datetime
from typing import Optional, Callable, TypeVar

import bcrypt
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import Employee, UserAccount

SessionFactory = Callable[[], Session]
TUserAccount = TypeVar("TUserAccount", bound=UserAccount)


class AuthController:
    """
    Authentication and user bootstrap logic.

    This controller works with SQLAlchemy sessions created via the configured
    session factory (default: app.database.SessionLocal).
    """

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory: SessionFactory = session_factory or SessionLocal

    def _get_session(self) -> Session:
        return self._session_factory()

    def login(self, username: str, password: str) -> Optional[UserAccount]:
        """
        Validate credentials and return the authenticated UserAccount.

        Returns None if the username/password combination is invalid or the
        account is locked.
        """
        if not username or not password:
            return None

        with self._get_session() as session:
            user: Optional[UserAccount] = (
                session.query(UserAccount)
                .filter(UserAccount.Username == username)
                .first()
            )

            if user is None:
                return None

            if user.IsLocked:
                return None

            password_bytes = password.encode("utf-8")
            stored_hash = user.PasswordHash.encode("utf-8")

            if not bcrypt.checkpw(password_bytes, stored_hash):
                return None

            user.LastLogin = datetime.utcnow()
            session.add(user)
            session.commit()

            return user

    def create_default_admin(self) -> None:
        """
        Ensure there is at least one user account.

        If the user_account table is empty, create a default 'admin' user
        with password 'admin123' and a minimal backing Employee record.
        """
        with self._get_session() as session:
            # If any user exists at all, don't create the default admin.
            has_any_user = session.query(UserAccount).first() is not None
            if has_any_user:
                return

            # If an 'admin' user already exists for some reason, do nothing.
            existing_admin = (
                session.query(UserAccount)
                .filter(UserAccount.Username == "admin")
                .first()
            )
            if existing_admin is not None:
                return

            # Reuse an existing synthetic employee if we find one with this mobile,
            # otherwise create a new Employee record.
            synthetic_mobile = "0000000000"
            employee: Optional[Employee] = (
                session.query(Employee)
                .filter(Employee.Mobile == synthetic_mobile)
                .first()
            )

            if employee is None:
                employee = Employee(
                    FirstName="System",
                    LastName="Administrator",
                    Mobile=synthetic_mobile,
                    IsActive=True,
                )
                session.add(employee)
                session.flush()  # assign EmpID

            raw_password = "admin123"
            hashed = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt())

            user = UserAccount(
                Username="admin",
                PasswordHash=hashed.decode("utf-8"),
                EmpID=employee.EmpID,
                IsLocked=False,
            )
            session.add(user)
            session.commit()