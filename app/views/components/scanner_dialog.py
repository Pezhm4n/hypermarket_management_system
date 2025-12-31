from __future__ import annotations

import logging
import os
from typing import Optional

import cv2
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    import winsound
except Exception:  # pragma: no cover - not available on non-Windows platforms
    winsound = None

from app.core.barcode_manager import BarcodeScanner
from app.core.translation_manager import TranslationManager

logger = logging.getLogger(__name__)


class VideoCaptureWorker(QThread):
    """
    QThread worker that grabs frames from the camera and scans them.
    """

    frame_ready = pyqtSignal(object)
    barcode_found = pyqtSignal(str)
    camera_error = pyqtSignal(str)

    def __init__(
        self,
        scanner: BarcodeScanner,
        camera_index: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._scanner = scanner
        self._camera_index = camera_index
        self._running = True

    def _find_working_camera(self):
        """
        Try camera indices with the MSMF backend and return the first
        working capture.
        """
        indices = [0, 1, 2]
        backend = getattr(cv2, "CAP_MSMF", cv2.CAP_ANY)
        backend_name = "MSMF"

        for idx in indices:
            if not self._running:
                return None, -1

            cap = None
            try:
                cap = cv2.VideoCapture(idx, backend)
                if not cap.isOpened():
                    cap.release()
                    continue

                # Force HD resolution to improve scan quality.
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                try:
                    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                except Exception:
                    # Some drivers may not support autofocus; ignore errors.
                    pass

                # Warmup frames
                valid = False
                for _ in range(3):
                    if not self._running:
                        break
                    ret, frame = cap.read()
                    if (
                        ret
                        and frame is not None
                        and hasattr(frame, "size")
                        and frame.size > 0
                    ):
                        valid = True
                        break

                if not valid or not self._running:
                    cap.release()
                    continue

                logger.info(
                    "Connected to Camera %s using %s", idx, backend_name
                )
                return cap, idx
            except Exception as exc:
                logger.error("Error probing camera %s: %s", idx, exc)
                if cap is not None:
                    cap.release()
                continue

        return None, -1

    def run(self) -> None:
        cap, idx = self._find_working_camera()

        if cap is None:
            if self._running:
                self.camera_error.emit("Camera not found")
            return

        self._camera_index = idx
        self._frame_counter = 0

        try:
            while self._running:
                ret, frame = cap.read()
                if not ret or frame is None:
                    self.msleep(50)
                    continue

                # Always send the original frame to the UI for preview
                self.frame_ready.emit(frame)

                # Throttle decoding to reduce load on ZBar/pyzbar and avoid crashes
                self._frame_counter += 1
                if self._frame_counter % 3 != 0:
                    self.msleep(30)
                    continue

                try:
                    # Work on a smaller copy to minimize potential issues in native code
                    h, w = frame.shape[:2]
                    if w > 640:
                        scale = 640.0 / float(w)
                        new_size = (640, max(1, int(h * scale)))
                        frame_for_decode = cv2.resize(frame, new_size)
                    else:
                        frame_for_decode = frame.copy()
                except Exception:
                    frame_for_decode = frame

                code = self._scanner.decode_frame(frame_for_decode)
                if code and self._running:
                    self.barcode_found.emit(code)
                    break

                self.msleep(30)
        except Exception as exc:
            logger.error("Worker loop error: %s", exc)
        finally:
            cap.release()

    def stop(self) -> None:
        self._running = False
        # Do not wait here to avoid blocking the UI; the loop will exit shortly.


class ScannerDialog(QDialog):
    """
    Smart barcode scanner dialog that works with a live camera feed if
    available, and falls back to loading an image from disk otherwise.
    """

    barcode_detected = pyqtSignal(str)

    def __init__(
        self,
        translator: Optional[TranslationManager] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._scanner = BarcodeScanner()
        self._worker: Optional[VideoCaptureWorker] = None
        self._found_barcode: Optional[str] = None
        # Prevent immediate re-scan of a previous frame on dialog reopen
        self._scan_enabled: bool = False

        self._build_ui()
        # NOTE: camera is started in showEvent, not here.

    # ------------------------------------------------------------------ #
    # UI helpers
    # ------------------------------------------------------------------ #
    def _tr(self, key: str, default: str) -> str:
        if self._translator is None:
            return default
        return self._translator.get(key, default)

    def _build_ui(self) -> None:
        self.setModal(True)
        self.setMinimumSize(640, 480)
        self.setWindowTitle(self._tr("scanner.dialog.title", "Scan Barcode"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.lblVideo = QLabel(self)
        self.lblVideo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblVideo.setMinimumSize(480, 320)
        self.lblVideo.setStyleSheet(
            "background-color: #000000; border: 1px solid #444444;"
        )
        layout.addWidget(self.lblVideo)

        self.lblStatus = QLabel(self)
        self.lblStatus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblStatus.setText(
            self._tr(
                "scanner.status.initializing",
                "Initializing camera ...",
            )
        )
        layout.addWidget(self.lblStatus)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.btnLoadImage = QPushButton(self)
        self.btnLoadImage.setText(
            self._tr("scanner.button.load_image", "Load Image")
        )
        button_row.addWidget(self.btnLoadImage)

        self.btnClose = QPushButton(self)
        self.btnClose.setText(self._tr("scanner.button.close", "Close"))
        button_row.addWidget(self.btnClose)

        layout.addLayout(button_row)

        self.btnLoadImage.clicked.connect(self._on_load_image_clicked)
        self.btnClose.clicked.connect(self.reject)

    # ------------------------------------------------------------------ #
    # Camera handling
    # ------------------------------------------------------------------ #
    def _start_camera(self) -> None:
        # Disable scanning briefly after (re)start to avoid instant reuse
        self._scan_enabled = False
        QTimer.singleShot(
            1000, lambda: setattr(self, "_scan_enabled", True)
        )

        # Ensure UI shows a loading state until first frame arrives
        if hasattr(self, "lblVideo") and self.lblVideo is not None:
            self.lblVideo.clear()
        if hasattr(self, "lblStatus") and self.lblStatus is not None:
            self.lblStatus.setText(
                self._tr(
                    "scanner.status.initializing",
                    "Starting camera ...",
                )
            )

        self._worker = VideoCaptureWorker(self._scanner, parent=self)
        self._worker.frame_ready.connect(self._on_frame_ready)
        self._worker.barcode_found.connect(self._on_barcode_from_camera)
        self._worker.camera_error.connect(self._on_camera_error)
        self._worker.start()

    def _stop_worker(self) -> None:
        if self._worker is not None:
            try:
                # Disconnect signals to prevent callbacks from a dead thread.
                try:
                    self._worker.barcode_found.disconnect()
                except Exception:
                    pass
                try:
                    self._worker.frame_ready.disconnect()
                except Exception:
                    pass
                try:
                    self._worker.camera_error.disconnect()
                except Exception:
                    pass

                self._worker.stop()
                self._worker.quit()
                self._worker.wait(200)
                self._worker.deleteLater()
            except Exception as exc:
                logger.exception("Error stopping VideoCaptureWorker: %s", exc)
            finally:
                self._worker = None

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _on_frame_ready(self, frame) -> None:
        try:
            if frame is None or not hasattr(frame, "shape"):
                return

            height, width = frame.shape[:2]
            if height == 0 or width == 0:
                return

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = QImage(
                rgb.data,
                width,
                height,
                rgb.strides[0],
                QImage.Format.Format_RGB888,
            )
            pixmap = QPixmap.fromImage(image)
            if not pixmap.isNull():
                # During the initial warmup period, keep the video area blank
                # so the user does not see a stale frame from a previous scan.
                if not self._scan_enabled:
                    return

                self.lblVideo.setPixmap(
                    pixmap.scaled(
                        self.lblVideo.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.lblStatus.setText(
                    self._tr("scanner.status.scanning", "Scanning...")
                )
        except Exception as exc:
            logger.exception("Error updating camera frame: %s", exc)

    def _on_camera_error(self, message: str) -> None:
        self.lblStatus.setText(
            message
            or self._tr(
                "scanner.status.no_camera",
                "Camera not found - Please load an image",
            )
        )
        self.lblVideo.clear()

    def _on_barcode_from_camera(self, code: str) -> None:
        # Ignore early or empty reads
        if not self._scan_enabled or not code:
            return

        self._found_barcode = code
        self._stop_worker()

        try:
            if winsound is not None:
                winsound.MessageBeep()
        except Exception:
            pass

        self.barcode_detected.emit(code)
        self.accept()

    def _on_load_image_clicked(self) -> None:
        try:
            last_dir = os.path.expanduser("~")
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                self._tr("scanner.dialog.open_title", "Select barcode image"),
                last_dir,
                "Images (*.png *.jpg *.jpeg *.bmp *.gif)",
            )
            if not file_path:
                return

            code = self._scanner.decode_image(file_path)
            if not code:
                QMessageBox.information(
                    self,
                    self._tr("dialog.info_title", "Information"),
                    self._tr(
                        "scanner.info.no_barcode",
                        "No barcode could be detected in the selected image.",
                    ),
                )
                return

            # Treat image-based scan the same as camera-based scan
            self._on_barcode_from_camera(code)
        except Exception as exc:
            logger.exception("Error while loading image for barcode scan: %s", exc)
            QMessageBox.critical(
                self,
                self._tr("dialog.error_title", "Error"),
                str(exc),
            )

    # ------------------------------------------------------------------ #
    # Qt events
    # ------------------------------------------------------------------ #
    def showEvent(self, event) -> None:  # type: ignore[override]
        """
        Reset state each time the dialog is shown so we always start fresh.
        Also clear any stale frame so the user does not see the previous image.
        """
        # Strict state reset before probing the camera
        self._found_barcode = None

        # Clear any previous pixmap immediately to avoid ghost frames
        if hasattr(self, "lblVideo") and self.lblVideo is not None:
            self.lblVideo.clear()
            # Optional: keep background black via stylesheet already set in _build_ui

        # Show explicit feedback while camera is initializing
        if hasattr(self, "lblStatus") and self.lblStatus is not None:
            self.lblStatus.setText(
                self._tr(
                    "scanner.status.initializing",
                    "Starting camera ...",
                )
            )

        self._stop_worker()
        self._start_camera()
        super().showEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._stop_worker()
        super().closeEvent(event)