from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication
from sqlalchemy.exc import SQLAlchemyError
from qt_material import apply_stylesheet

from app.database import engine
from app.models.models import Base  # importing this registers all model classes
from app.controllers.auth_controller import AuthController
from app.views.login_view import LoginView
from app.views.main_view import MainView


def init_database() -> None:
    try:
        # Create all tables defined on Base.metadata
        Base.metadata.create_all(bind=engine)
        print("Database Connection Successful & Tables Created")
    except SQLAlchemyError as exc:
        # In Phase 1 we just print; later you may log this properly.
        print("Database initialization failed:", exc)


def main() -> None:
    # Initialize database schema
    init_database()

    # Ensure a default admin account exists if the user table is empty
    auth_controller = AuthController()
    auth_controller.create_default_admin()

    # Start Qt application
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme="dark_teal.xml")

    login_view = LoginView(auth_controller)
    main_view = MainView()

    def handle_login_success(user) -> None:
        main_view.set_logged_in_user(user)
        main_view.show()
        login_view.close()

    login_view.login_success.connect(handle_login_success)

    login_view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()