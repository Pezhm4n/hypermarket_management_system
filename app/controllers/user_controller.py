from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import bcrypt
import logging
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import Employee, Role, UserAccount, UserRole

SessionFactory = Callable[[], Session]

logger = logging.getLogger(__name__)

DEFAULT_ROLE_TITLES: tuple[str, ...] = ("Admin", "Cashier", "StoreKeeper")


class UserController:
    """
    Business logic for managing Employee and UserAccount records.

    Provides CRUD operations used by the Users management UI.
    """

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory: SessionFactory = session_factory or SessionLocal

    def _get_session(self) -> Session:
        return self._session_factory()

    # ------------------------------------------------------------------ #
    # Role helpers
    # ------------------------------------------------------------------ #
    def _get_or_create_role(self, session: Session, title: str) -> Role:
        title = title.strip()
        if not title:
            raise ValueError("Role title must not be empty.")

        role = session.query(Role).filter(Role.Title == title).first()
        if role is not None:
            return role

        role = Role(Title=title)
        session.add(role)
        session.flush()
        return role

    def list_roles(self) -> List[str]:
        """
        Return all available role titles.

        If no roles exist yet, a small default set is created.
        """
        with self._get_session() as session:
            with session.begin():
                roles = session.query(Role).order_by(Role.Title).all()
                if not roles:
                    for title in DEFAULT_ROLE_TITLES:
                        session.add(Role(Title=title))
                    session.flush()
                    roles = session.query(Role).order_by(Role.Title).all()

                return [r.Title for r in roles]

    # ------------------------------------------------------------------ #
    # User listing / lookup
    # ------------------------------------------------------------------ #
    def list_users(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Return a list of users for display in the Users table.

        Each row is a dict with:
            user_id, emp_id, full_name, username, role, mobile, status, is_locked
        """
        with self._get_session() as session:
            query = (
                session.query(UserAccount, Employee, Role)
                .join(Employee, UserAccount.EmpID == Employee.EmpID)
                .outerjoin(UserRole, UserRole.UserID == UserAccount.UserID)
                .outerjoin(Role, UserRole.RoleID == Role.RoleID)
            )

            if search:
                term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        UserAccount.Username.ilike(term),
                        Employee.FirstName.ilike(term),
                        Employee.LastName.ilike(term),
                        Employee.Mobile.ilike(term),
                    )
                )

            rows = query.order_by(Employee.LastName, Employee.FirstName).all()

            results: List[Dict[str, Any]] = []
            for user, employee, role in rows:
                full_name = f"{employee.FirstName} {employee.LastName}".strip()
                role_title = role.Title if role is not None else ""
                is_active_employee = (
                    bool(employee.IsActive) if employee.IsActive is not None else True
                )
                active = not bool(user.IsLocked) and is_active_employee
                status = "Active" if active else "Locked"

                results.append(
                    {
                        "user_id": user.UserID,
                        "emp_id": employee.EmpID,
                        "full_name": full_name,
                        "username": user.Username,
                        "role": role_title,
                        "mobile": employee.Mobile,
                        "status": status,
                        "is_locked": bool(user.IsLocked),
                    }
                )

            return results

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a single user and related employee/role information.
        """
        with self._get_session() as session:
            user: Optional[UserAccount] = session.get(UserAccount, user_id)
            if user is None:
                return None

            employee: Optional[Employee] = user.employee
            if employee is None:
                # Database invariant should prevent this, but guard regardless.
                return None

            primary_user_role: Optional[UserRole] = (
                user.user_roles[0] if user.user_roles else None
            )
            role_title = (
                primary_user_role.role.Title
                if primary_user_role is not None and primary_user_role.role is not None
                else ""
            )

            return {
                "user_id": user.UserID,
                "emp_id": employee.EmpID,
                "first_name": employee.FirstName,
                "last_name": employee.LastName,
                "mobile": employee.Mobile,
                "username": user.Username,
                "role": role_title,
                "is_locked": bool(user.IsLocked),
            }

    # ------------------------------------------------------------------ #
    # CRUD operations
    # ------------------------------------------------------------------ #
    def create_user(
        self,
        first_name: str,
        last_name: str,
        mobile: str,
        username: str,
        password: str,
        role_title: str,
    ) -> UserAccount:
        """
        Create a new Employee + UserAccount + UserRole in a single transaction.
        """
        first_name = first_name.strip()
        last_name = last_name.strip()
        mobile = mobile.strip()
        username = username.strip()
        role_title = role_title.strip()

        if not first_name or not last_name or not mobile or not username:
            raise ValueError("All fields except password are required.")
        if not password:
            raise ValueError("Password is required for new users.")
        if not role_title:
            raise ValueError("Role is required for new users.")

        with self._get_session() as session:
            with session.begin():
                # Uniqueness checks
                existing_user = (
                    session.query(UserAccount)
                    .filter(UserAccount.Username == username)
                    .first()
                )
                if existing_user is not None:
                    raise ValueError("Username is already taken.")

                existing_emp = (
                    session.query(Employee)
                    .filter(Employee.Mobile == mobile)
                    .first()
                )
                if existing_emp is not None:
                    raise ValueError("Mobile number is already used for another employee.")

                employee = Employee(
                    FirstName=first_name,
                    LastName=last_name,
                    Mobile=mobile,
                    IsActive=True,
                )
                session.add(employee)
                session.flush()  # assign EmpID

                hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
                user = UserAccount(
                    Username=username,
                    PasswordHash=hashed.decode("utf-8"),
                    EmpID=employee.EmpID,
                    IsLocked=False,
                )
                session.add(user)
                session.flush()  # assign UserID

                role = self._get_or_create_role(session, role_title)
                user_role = UserRole(UserID=user.UserID, RoleID=role.RoleID)
                session.add(user_role)

                logger.info(
                    "Created user '%s' (EmpID=%s, Role='%s')",
                    username,
                    employee.EmpID,
                    role_title,
                )

                return user

    def update_user(
        self,
        user_id: int,
        first_name: str,
        last_name: str,
        mobile: str,
        username: str,
        new_password: Optional[str],
        role_title: str,
    ) -> None:
        """
        Update Employee + UserAccount (+ primary UserRole) details.
        """
        first_name = first_name.strip()
        last_name = last_name.strip()
        mobile = mobile.strip()
        username = username.strip()
        role_title = role_title.strip()

        if not first_name or not last_name or not mobile or not username:
            raise ValueError("All fields except password are required.")
        if not role_title:
            raise ValueError("Role is required.")

        with self._get_session() as session:
            with session.begin():
                user: Optional[UserAccount] = session.get(UserAccount, user_id)
                if user is None:
                    raise ValueError("User not found.")

                employee: Optional[Employee] = user.employee
                if employee is None:
                    raise ValueError("Related employee record not found.")

                # Uniqueness checks
                existing_user = (
                    session.query(UserAccount)
                    .filter(
                        UserAccount.Username == username,
                        UserAccount.UserID != user_id,
                    )
                    .first()
                )
                if existing_user is not None:
                    raise ValueError("Username is already taken by another user.")

                existing_emp = (
                    session.query(Employee)
                    .filter(
                        Employee.Mobile == mobile,
                        Employee.EmpID != employee.EmpID,
                    )
                    .first()
                )
                if existing_emp is not None:
                    raise ValueError(
                        "Mobile number is already used for another employee."
                    )

                employee.FirstName = first_name
                employee.LastName = last_name
                employee.Mobile = mobile

                user.Username = username

                if new_password:
                    hashed = bcrypt.hashpw(
                        new_password.encode("utf-8"),
                        bcrypt.gensalt(),
                    )
                    user.PasswordHash = hashed.decode("utf-8")

                # Update primary role (we treat first as primary)
                role = self._get_or_create_role(session, role_title)
                # Remove existing roles
                for user_role in list(user.user_roles):
                    session.delete(user_role)
                # Attach new role
                session.add(UserRole(UserID=user.UserID, RoleID=role.RoleID))

                logger.info(
                    "Updated user '%s' (UserID=%s, EmpID=%s, Role='%s')",
                    username,
                    user.UserID,
                    employee.EmpID,
                    role_title,
                )

    def delete_user(self, user_id: int) -> None:
        """
        Soft-delete a user by locking the account and deactivating the employee.

        This avoids breaking historical references (e.g. invoices linked to the
        employee) while effectively removing login access.
        """
        with self._get_session() as session:
            with session.begin():
                user: Optional[UserAccount] = session.get(UserAccount, user_id)
                if user is None:
                    return

                employee: Optional[Employee] = user.employee

                user.IsLocked = True
                if employee is not None:
                    employee.IsActive = False

                logger.info(
                    "Soft-deleted user '%s' (UserID=%s)",
                    user.Username,
                    user.UserID,
                )