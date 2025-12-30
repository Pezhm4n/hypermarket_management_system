import sys
from PyQt6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from app.database import engine
from app.models.models import Base
from app.controllers.auth_controller import AuthController
from app.views.login_view import LoginView
from app.views.main_view import MainView


def init_database():
    """ساخت جداول دیتابیس در صورت عدم وجود"""
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database Connection Successful & Tables Created")
    except Exception as e:
        print(f"❌ Database Error: {e}")
        sys.exit(1)


def main():
    # ۱. آماده‌سازی دیتابیس
    init_database()

    # ۲. ایجاد کنترلر احراز هویت و یوزر ادمین پیش‌فرض
    auth_controller = AuthController()
    auth_controller.create_default_admin()

    # ۳. اجرای اپلیکیشن PyQt6
    app = QApplication(sys.argv)

    # اعمال تم ظاهری (اختیاری)
    apply_stylesheet(app, theme='dark_teal.xml')

    # ۴. ایجاد ویوها (Views)
    login_view = LoginView(auth_controller)
    main_view = MainView()

    # ۵. مدیریت جابجایی بین پنجره‌ها
    def handle_login_success(user):
        print(f"👤 Welcome, {user.Username}!")
        main_view.set_logged_in_user(user)
        main_view.show()
        login_view.close()

    login_view.login_success.connect(handle_login_success)

    # ۶. نمایش صفحه لاگین
    login_view.show()

    # اجرای حلقه اصلی برنامه
    sys.exit(app.exec())


if __name__ == "__main__":
    main()