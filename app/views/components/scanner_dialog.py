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
    QCheckBox,
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
        use_droidcam: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._scanner = scanner
        self._use_droidcam = use_droidcam
        self._running = False
        self._cap = None

    def _find_working_camera(self):
        """
        Try to find and open a working camera based on user preference.
        """
        if self._use_droidcam:
            # اولویت با DroidCam: ایندکس‌های 1, 2, 3
            indices = [1, 2, 3]
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF]
            camera_type = "DroidCam/External"
        else:
            # اولویت با Webcam داخلی: ایندکس 0
            indices = [0]
            backends = [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]
            camera_type = "Internal Webcam"
        
        logger.info(f"Searching for {camera_type}...")
        
        for idx in indices:
            for backend in backends:
                if not self._running:
                    return None, -1
                    
                cap = None
                try:
                    backend_name = {
                        cv2.CAP_DSHOW: "DSHOW",
                        cv2.CAP_MSMF: "MSMF",
                        cv2.CAP_ANY: "ANY"
                    }.get(backend, str(backend))
                    
                    logger.debug(f"Trying Camera {idx} with backend {backend_name}")
                    
                    # تلاش برای باز کردن دوربین
                    cap = cv2.VideoCapture(idx, backend)
                    
                    if not cap.isOpened():
                        if cap is not None:
                            cap.release()
                        continue

                    # تنظیم کیفیت تصویر
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # تست خواندن فریم - چند بار تلاش می‌کنیم
                    success = False
                    for attempt in range(3):
                        ret, frame = cap.read()
                        if ret and frame is not None and frame.size > 0:
                            success = True
                            break
                        self.msleep(100)
                    
                    if success:
                        logger.info(
                            f"✓ Successfully connected to Camera {idx} "
                            f"using backend {backend_name} ({camera_type})"
                        )
                        return cap, idx
                    else:
                        logger.debug(f"Camera {idx} opened but failed to read frames")
                        cap.release()
                        
                except Exception as exc:
                    logger.debug(f"Failed Camera {idx} with backend {backend_name}: {exc}")
                    if cap is not None:
                        try:
                            cap.release()
                        except:
                            pass
                    continue
        
        logger.error(f"No working {camera_type} found")
        return None, -1

    def run(self) -> None:
        self._running = True
        
        cap, idx = self._find_working_camera()

        if cap is None:
            if self._running:
                camera_type = "DroidCam" if self._use_droidcam else "Internal Webcam"
                self.camera_error.emit(f"{camera_type} not found")
            return

        self._cap = cap
        self._frame_counter = 0

        try:
            while self._running:
                if not self._cap or not self._cap.isOpened():
                    break
                    
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    self.msleep(50)
                    continue

                # Always send the original frame to the UI for preview
                if self._running:
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
            self._cleanup_camera()

    def _cleanup_camera(self):
        """آزاد سازی منابع دوربین"""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception as exc:
                logger.error(f"Error releasing camera: {exc}")
            finally:
                self._cap = None

    def stop(self) -> None:
        """متوقف کردن thread به صورت ایمن"""
        self._running = False


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
        self._scan_enabled: bool = False
        self._camera_started: bool = False  # برای چک کردن آیا دوربین شروع شده یا نه

        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI helpers
    # ------------------------------------------------------------------ #
    def _tr(self, key: str, default: str) -> str:
        if self._translator is None:
            return default
        return self._translator.get(key, default)

    def _build_ui(self) -> None:
        self.setModal(True)

        if self._translator and self._translator.language == "fa":
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self.setMinimumSize(640, 560)
        self.setWindowTitle(self._tr("scanner.dialog.title", "Scan Barcode"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Camera selection checkbox - در بالای همه
        camera_selection_layout = QHBoxLayout()
        camera_selection_layout.setSpacing(12)
        
        self.chkUseDroidCam = QCheckBox(self)
        self.chkUseDroidCam.setText(
            self._tr("scanner.checkbox.use_droidcam", "Use DroidCam (External Camera)")
        )
        self.chkUseDroidCam.setChecked(False)  # پیش‌فرض: Webcam داخلی
        self.chkUseDroidCam.setStyleSheet("font-weight: bold;")
        camera_selection_layout.addWidget(self.chkUseDroidCam)
        
        # دکمه شروع دوربین
        self.btnStartCamera = QPushButton(self)
        self.btnStartCamera.setText(
            self._tr("scanner.button.start_camera", "Start Camera")
        )
        self.btnStartCamera.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.btnStartCamera.clicked.connect(self._on_start_camera_clicked)
        camera_selection_layout.addWidget(self.btnStartCamera)
        
        camera_selection_layout.addStretch()
        layout.addLayout(camera_selection_layout)

        # Video preview area
        self.lblVideo = QLabel(self)
        self.lblVideo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblVideo.setMinimumSize(480, 320)
        self.lblVideo.setStyleSheet(
            "background-color: #000000; border: 1px solid #444444;"
        )
        self.lblVideo.setText(
            self._tr(
                "scanner.label.select_camera",
                "Select camera type and click 'Start Camera'"
            )
        )
        layout.addWidget(self.lblVideo)

        # Status label
        self.lblStatus = QLabel(self)
        self.lblStatus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblStatus.setText(
            self._tr(
                "scanner.status.ready",
                "Ready to scan",
            )
        )
        layout.addWidget(self.lblStatus)

        # Buttons
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
    def _on_start_camera_clicked(self) -> None:
        """وقتی کاربر دکمه Start Camera را میزند"""
        # اگر دوربین در حال کار است، آن را متوقف کرده و دوباره شروع کنیم
        if self._camera_started:
            self._stop_worker()
            QTimer.singleShot(300, lambda: self._start_camera(use_droidcam=self.chkUseDroidCam.isChecked()))
        else:
            self._start_camera(use_droidcam=self.chkUseDroidCam.isChecked())

    def _start_camera(self, use_droidcam: bool = False) -> None:
        """شروع دوربین با توجه به انتخاب کاربر"""
        self._camera_started = True
        
        # Disable scanning briefly after (re)start to avoid instant reuse
        self._scan_enabled = False
        QTimer.singleShot(
            1000, lambda: setattr(self, "_scan_enabled", True)
        )

        # Clear UI
        if hasattr(self, "lblVideo") and self.lblVideo is not None:
            self.lblVideo.clear()
        
        # --- بخش اصلاح شده برای ترجمه ---
        # 1. ابتدا نام نوع دوربین را ترجمه می‌کنیم
        if use_droidcam:
            camera_name = self._tr("scanner.camera_type.droidcam", "DroidCam")
        else:
            camera_name = self._tr("scanner.camera_type.webcam", "Webcam")

        if hasattr(self, "lblStatus") and self.lblStatus is not None:
            # 2. دریافت قالب پیام از فایل JSON
            # مثال فارسی در فایل جیسون: "در حال راه‌اندازی {camera_type}..."
            msg_template = self._tr(
                "scanner.status.initializing",
                "Starting {camera_type}..."
            )
            # 3. جایگذاری نام دوربین در متن پیام
            final_message = msg_template.replace("{camera_type}", camera_name)
            self.lblStatus.setText(final_message)
        # -------------------------------

        # غیرفعال کردن controls در حین اتصال
        self.chkUseDroidCam.setEnabled(False)
        self.btnStartCamera.setEnabled(False)
        self.btnStartCamera.setText(
            self._tr("scanner.button.connecting", "Connecting...")
        )

        self._worker = VideoCaptureWorker(
            self._scanner, 
            use_droidcam=use_droidcam,
            parent=self
        )
        self._worker.frame_ready.connect(self._on_frame_ready)
        self._worker.barcode_found.connect(self._on_barcode_from_camera)
        self._worker.camera_error.connect(self._on_camera_error)
        self._worker.start()

    def _stop_worker(self) -> None:
        """متوقف کردن worker thread به صورت ایمن و کامل"""
        if self._worker is not None:
            try:
                # ابتدا سیگنال stop را ارسال کنیم
                self._worker.stop()
                
                # Disconnect signals to prevent callbacks from a dead thread
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

                # منتظر می‌مانیم تا thread به طور کامل متوقف شود
                if self._worker.isRunning():
                    self._worker.quit()
                    if not self._worker.wait(2000):  # 2 ثانیه timeout
                        logger.warning("Worker thread did not stop gracefully, terminating...")
                        self._worker.terminate()
                        self._worker.wait(1000)
                
                # پاکسازی نهایی
                self._worker.deleteLater()
                
            except Exception as exc:
                logger.exception("Error stopping VideoCaptureWorker: %s", exc)
            finally:
                self._worker = None
                self._camera_started = False
                # فعال کردن مجدد controls
                self.chkUseDroidCam.setEnabled(True)
                self.btnStartCamera.setEnabled(True)
                self.btnStartCamera.setText(
                    self._tr("scanner.button.start_camera", "Start Camera")
                )

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
                if not self._scan_enabled:
                    return
                self.lblVideo.setPixmap(
                    pixmap.scaled(
                        self.lblVideo.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

                # --- اصلاح بخش ترجمه ---
                # 1. ترجمه نام دوربین
                if self.chkUseDroidCam.isChecked():
                    camera_name = self._tr("scanner.camera_type.droidcam", "DroidCam")
                else:
                    camera_name = self._tr("scanner.camera_type.webcam", "Webcam")

                # 2. دریافت قالب پیام و جایگذاری نام دوربین
                msg_template = self._tr("scanner.status.scanning", "Scanning with {camera_type}...")
                final_msg = msg_template.replace("{camera_type}", camera_name)
                
                self.lblStatus.setText(final_msg)
                # -----------------------
                
                # تغییر متن دکمه به Restart
                if self.btnStartCamera.isEnabled() == False:
                    self.btnStartCamera.setEnabled(True)
                    self.btnStartCamera.setText(
                        self._tr("scanner.button.restart_camera", "Restart Camera")
                    )
                    self.chkUseDroidCam.setEnabled(True)
                    
        except Exception as exc:
            logger.exception("Error updating camera frame: %s", exc)

    def _on_camera_error(self, message: str) -> None:
        self.lblStatus.setText(
            message
            or self._tr(
                "scanner.status.no_camera",
                "Camera not found - Please try another option or load an image",
            )
        )
        self.lblVideo.clear()
        self.lblVideo.setText(
            self._tr(
                "scanner.label.camera_error",
                "Camera not found!\nTry changing the camera type or load an image."
            )
        )
        # فعال کردن مجدد controls در صورت خطا
        self.chkUseDroidCam.setEnabled(True)
        self.btnStartCamera.setEnabled(True)
        self.btnStartCamera.setText(
            self._tr("scanner.button.start_camera", "Start Camera")
        )
        self._camera_started = False

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
        """
        self._found_barcode = None
        self._camera_started = False

        # Clear any previous pixmap
        if hasattr(self, "lblVideo") and self.lblVideo is not None:
            self.lblVideo.clear()
            self.lblVideo.setText(
                self._tr(
                    "scanner.label.select_camera",
                    "Select camera type and click 'Start Camera'"
                )
            )

        # Reset status
        if hasattr(self, "lblStatus") and self.lblStatus is not None:
            self.lblStatus.setText(
                self._tr(
                    "scanner.status.ready",
                    "Ready to scan",
                )
            )

        # Reset controls
        if hasattr(self, "btnStartCamera"):
            self.btnStartCamera.setEnabled(True)
            self.btnStartCamera.setText(
                self._tr("scanner.button.start_camera", "Start Camera")
            )
        if hasattr(self, "chkUseDroidCam"):
            self.chkUseDroidCam.setEnabled(True)

        # Stop any existing worker
        self._stop_worker()
        
        super().showEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """بستن ایمن دیالوگ با اطمینان از آزادسازی تمام منابع"""
        self._stop_worker()
        
        if hasattr(self, "lblVideo") and self.lblVideo is not None:
            self.lblVideo.clear()
        
        super().closeEvent(event)
        
    def reject(self) -> None:
        """Override reject to ensure proper cleanup"""
        self._stop_worker()
        super().reject()
        
    def accept(self) -> None:
        """Override accept to ensure proper cleanup"""
        self._stop_worker()
        super().accept()