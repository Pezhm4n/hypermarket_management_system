from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional, TypeVar

import bcrypt
import logging
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import Employee, UserAccount

SessionFactory = Callable[[], Session]
TUserAccount = TypeVar("TUserAccount", bound=UserAccount)

logger = logging.getLogger(__name__)


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
                logger.info("Login failed: unknown username '%s'", username)
                return None

            if user.IsLocked:
                logger.warning("Login attempt for locked account '%s'", username)
                return None

            password_bytes = password.encode("utf-8")
            stored_hash = user.PasswordHash.encode("utf-8")

            if not bcrypt.checkpw(password_bytes, stored_hash):
                logger.info("Login failed: invalid password for '%s'", username)
                return None

            user.LastLogin = datetime.utcnow()
            session.add(user)
            session.commit()

            logger.info("User '%s' logged in successfully.", username)
            return user

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> bool:
        """
        Change the password for a given user.

        Returns True if the password was changed successfully, or False if the
        current password is incorrect or the user could not be found.
        """
        if not current_password or not new_password:
            raise ValueError("Passwords must not be empty.")

        with self._get_session() as session:
            user: Optional[UserAccount] = session.get(UserAccount, user_id)
            if user is None:
                logger.warning(
                    "Password change requested for unknown user_id=%s",
                    user_id,
                )
                return False

            if user.IsLocked:
                logger.warning(
                    "Password change requested for locked user '%s'",
                    user.Username,
                )
                return False

            password_bytes = current_password.encode("utf-8")
            stored_hash = user.PasswordHash.encode("utf-8")

            if not bcrypt.checkpw(password_bytes, stored_hash):
                logger.info(
                    "Password change failed: incorrect current password for '%s'",
                    user.Username,
                )
                return False

            new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
            user.PasswordHash = new_hash.decode("utf-8")
            session.add(user)
            session.commit()

            logger.info("Password changed successfully for user '%s'", user.Username)
            return True

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
            logger.info("Default admin user 'admin' ensured in database.")