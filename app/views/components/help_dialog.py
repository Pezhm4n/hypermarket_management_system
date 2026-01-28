from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QTextDocument, QAction
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.translation_manager import TranslationManager
from app.utils import resource_path


class HelpDialog(QDialog):
    """
    A robust Help Dialog that forces HTML manipulation to fix Qt's weak CSS support.
    """

    def __init__(
            self,
            translation_manager: TranslationManager,
            parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translation_manager

        # متغیرهای وضعیت
        self._raw_markdown = ""  # متن اصلی مارک‌داون
        self._show_images = True
        self._current_zoom = 0  # سطح زوم پیش‌فرض

        # تنظیمات پنجره
        self.setModal(True)
        self.setMinimumSize(900, 700)

        # جهت‌چین (RTL/LTR)
        is_farsi = getattr(self._translator, "language", "fa") == "fa"
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if is_farsi else Qt.LayoutDirection.LeftToRight
        )

        self.setWindowTitle(self._translator.get("help.window_title", "Help"))

        logo_path = resource_path("app/assets/logo.png")
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        self._build_ui()
        self._load_markdown_file()
        self._render_content()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # حذف حاشیه‌های اضافی دیالوگ
        layout.setSpacing(0)

        # --- نوار ابزار بالا (Toolbar) ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #2d2d2d; border-bottom: 1px solid #3d3d3d;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(15, 10, 15, 10)

        # عنوان
        title = QLabel(self._translator.get("help.dialog.title", "PeMa Manager Help"))
        title.setStyleSheet("font-weight: bold; font-size: 14pt; color: #4db8ff;")
        tb_layout.addWidget(title, stretch=1)

        # چک‌باکس نمایش عکس
        self.toggle_images = QCheckBox(self._translator.get("help.toggle_images", "Show Images"))
        self.toggle_images.setChecked(True)
        self.toggle_images.setStyleSheet("color: #ffffff; font-size: 10pt;")
        self.toggle_images.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_images.toggled.connect(self._on_toggle_images)
        tb_layout.addWidget(self.toggle_images)

        # فاصله
        tb_layout.addSpacing(20)

        # دکمه‌های زوم
        btn_style = """
            QPushButton {
                background-color: #444; color: white; border-radius: 4px; padding: 5px 10px; font-weight: bold;
            }
            QPushButton:hover { background-color: #555; }
            QPushButton:pressed { background-color: #666; }
        """

        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setFixedSize(30, 30)
        self.btn_zoom_out.setStyleSheet(btn_style)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        tb_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedSize(30, 30)
        self.btn_zoom_in.setStyleSheet(btn_style)
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        tb_layout.addWidget(self.btn_zoom_in)

        layout.addWidget(toolbar)

        # --- نمایشگر متن ---
        self.viewer = QTextBrowser(self)
        self.viewer.setOpenExternalLinks(True)
        self.viewer.setFrameShape(QTextBrowser.Shape.NoFrame)
        # استایل‌دهی به اسکرول‌بار و پس‌زمینه اصلی
        self.viewer.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                color: #e0e0e0;
                selection-background-color: #4db8ff;
                selection-color: #000000;
                padding: 20px;
            }
        """)
        layout.addWidget(self.viewer)

        # --- دکمه بستن پایین ---
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(15, 10, 15, 15)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        # استایل دکمه بستن
        buttons.setStyleSheet("""
            QPushButton {
                background-color: #c62828; color: white; border: none; padding: 8px 20px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        footer_layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(footer)

    def _load_markdown_file(self) -> None:
        """فایل را می‌خواند و در حافظه نگه می‌دارد."""
        language = getattr(self._translator, "language", "fa")
        filename = "fa_help.md" if language == "fa" else "en_help.md"
        md_path = resource_path(filename)

        if not md_path.exists():
            error_msg = self._translator.get("help.missing_file", "File not found.").format(filename=filename)
            self._raw_markdown = f"# Error\n\n{error_msg}"
        else:
            try:
                self._raw_markdown = md_path.read_text(encoding="utf-8")
            except Exception as e:
                self._raw_markdown = f"# Error\n\nCould not read file: {e}"

    def _render_content(self) -> None:
        """
        مارک‌داون را به HTML تبدیل کرده و تگ‌های عکس را اصلاح می‌کند.
        """
        content_to_render = self._raw_markdown

        # 1. مدیریت نمایش/مخفی عکس در سطح مارک‌داون (قبل از تبدیل به HTML)
        # اگر کاربر عکس نخواهد، تمام پترن‌های ![alt](src) را حذف می‌کنیم.
        if not self._show_images:
            # پترن مارک‌داون برای عکس: ![description](url)
            content_to_render = re.sub(r'!\[.*?\]\(.*?\)', '', content_to_render)

        # 2. تبدیل مارک‌داون به HTML با استفاده از موتور داخلی Qt
        doc = QTextDocument()
        doc.setMarkdown(content_to_render)
        html = doc.toHtml()

        # 3. دستکاری HTML برای اصلاح سایز عکس‌ها (این بخش حیاتی است)
        # Qt ویژگی width را در تگ img می‌فهمد، اما CSS max-width را نه.
        # پس ما width="80%" را به تمام تگ‌های img تزریق می‌کنیم.
        if self._show_images:
            # پیدا کردن تگ‌های img و اضافه کردن width اگر وجود نداشته باشد
            # این ریجکس ساده تگ img src="..." را پیدا کرده و width را اضافه می‌کند
            html = re.sub(r'(<img\s+src="[^"]+")', r'\1 width="500"', html)
            # نکته: عدد 500 پیکسل معمولاً در دیالوگ‌ها خوب است. یا می‌توان از width="100%" استفاده کرد
            # اما width="100%" گاهی در Qt باعث کشیده شدن ارتفاع می‌شود. عدد ثابت امن‌تر است.

        # 4. تزریق CSS برای فونت و رنگ‌بندی (چون QTextBrowser استایل ویجت را کامل به ارث نمی‌برد)
        base_css = """
        <style>
            body { font-family: 'Segoe UI', Tahoma, sans-serif; font-size: 14pt; line-height: 1.6; }
            h1 { color: #4db8ff; font-size: 22pt; margin-top: 0; margin-bottom: 20px; text-decoration: underline; }
            h2 { color: #81d4fa; font-size: 18pt; margin-top: 30px; margin-bottom: 10px; }
            h3 { color: #b3e5fc; font-size: 16pt; margin-top: 20px; }
            p { margin-bottom: 15px; }
            code { background-color: #333; color: #ffa726; padding: 2px 5px; border-radius: 4px; }
            a { color: #29b6f6; text-decoration: none; }
            ul, ol { margin-left: 20px; }
            li { margin-bottom: 5px; }
        </style>
        """

        # ترکیب CSS با HTML
        final_html = base_css + html

        # نمایش
        self.viewer.setHtml(final_html)

        # بازیابی زوم قبلی (چون setHtml زوم را ریست می‌کند)
        # ما زوم را با تابع zoomIn/Out مدیریت می‌کنیم، نه CSS
        current_zoom = self._current_zoom
        # ریست کردن زوم ویجت به صفر و اعمال دوباره
        self.viewer.zoomOut(100)  # زوم را کاملا ریست کن
        if current_zoom > 0:
            self.viewer.zoomIn(current_zoom)
        elif current_zoom < 0:
            self.viewer.zoomOut(abs(current_zoom))

    def _on_toggle_images(self, checked: bool) -> None:
        self._show_images = checked
        self._render_content()

    def _zoom_in(self) -> None:
        self.viewer.zoomIn(1)
        self._current_zoom += 1

    def _zoom_out(self) -> None:
        self.viewer.zoomOut(1)
        self._current_zoom -= 1