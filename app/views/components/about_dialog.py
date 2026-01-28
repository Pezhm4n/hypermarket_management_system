from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.core.translation_manager import TranslationManager
from app.utils import resource_path


class AboutDialog(QDialog):
    """Simple "About" dialog with application identity and credits."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._translator: Optional[TranslationManager] = None
        if parent is not None:
            candidate = getattr(parent, "_translator", None) or getattr(
                parent, "translation_manager", None
            )
            if isinstance(candidate, TranslationManager):
                self._translator = candidate

        self.setModal(True)
        language = getattr(self._translator, "language", "fa")
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
            if language == "fa"
            else Qt.LayoutDirection.LeftToRight
        )
        self.setWindowTitle(
            self._t("about.window_title", "About PeMa Manager")
        )
        self.setMinimumWidth(520)

        logo_path = resource_path("app/assets/logo.png")
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        self._build_ui(logo_path)

    def _t(self, key: str, fallback: str) -> str:
        if self._translator is None:
            return fallback
        return self._translator.get(key, fallback)

    def _build_ui(self, logo_path) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # Header with logo + app name
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        # Logo
        logo_label = QLabel(self)
        if logo_path and logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                logo_label.setPixmap(
                    pixmap.scaled(
                        96,
                        96,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        header_row.addWidget(logo_label)

        # App name / version
        title_container = QWidget(self)
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)

        lbl_name = QLabel(
            self._t("about.app_name", "PeMa Manager (Persian Market)"),
            title_container,
        )
        font = QFont(lbl_name.font())
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        lbl_name.setFont(font)

        lbl_version = QLabel(
            self._t("about.version", "Application version: v1.0.0"),
            title_container,
        )
        lbl_year = QLabel(
            self._t("about.year", "Development year: 2026"),
            title_container,
        )

        title_layout.addWidget(lbl_name)
        title_layout.addWidget(lbl_version)
        title_layout.addWidget(lbl_year)
        title_layout.addStretch()

        header_row.addWidget(title_container, stretch=1)
        layout.addLayout(header_row)

        # Developers section
        dev_title = QLabel(
            self._t("about.developers.title", "Developers:"),
            self,
        )
        dev_title_font = QFont(dev_title.font())
        dev_title_font.setBold(True)
        dev_title.setFont(dev_title_font)
        layout.addWidget(dev_title)

        dev1 = QLabel(self)
        dev1.setText(
            self._t(
                "about.developers.primary",
                "<b>Pezhm4n</b> &amp; <b>HTIcodes</b>",
            )
        )
        dev1.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(dev1)

        links1 = QLabel(self)
        links1.setText(
            self._t(
                "about.links.primary",
                (
                    'GitHub: <a href="https://github.com/Pezhm4n" style="color:#4db8ff;">github.com/Pezhm4n</a><br>'
                    'LinkedIn: <a href="https://www.linkedin.com/in/pezhman-sarmadi/" style="color:#4db8ff;">pezhman-sarmadi</a><br>'
                    'Email: <a href="mailto:pksarmadi@gmail.com" style="color:#4db8ff;">pksarmadi@gmail.com</a>'
                ),
            )
        )
        links1.setOpenExternalLinks(True)
        links1.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(links1)

        links2 = QLabel(self)
        links2.setText(
            self._t(
                "about.links.secondary",
                (
                    'GitHub: <a href="https://github.com/HTIcodes" style="color:#4db8ff;">github.com/HTIcodes</a><br>'
                    'LinkedIn: <a href="https://www.linkedin.com/in/mahyar-hemmati-0a81a1320/" style="color:#4db8ff;">mahyar-hemmati</a>'
                ),
            )
        )
        links2.setOpenExternalLinks(True)
        links2.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(links2)

        # Ensure links are clearly visible on dark backgrounds
        links1.setStyleSheet("color: #4db8ff;")
        links2.setStyleSheet("color: #4db8ff;")

        dev3 = QLabel(
            self._t(
                "about.developers.third",
                "Developer: Chupolovski",
            ),
            self,
        )
        layout.addWidget(dev3)

        # Disclaimer
        disclaimer = QLabel(
            self._t(
                "about.disclaimer",
                "The operator is responsible for verifying the correctness of invoice amounts.",
            ),
            self,
        )
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        layout.addStretch()

        # Close button
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
