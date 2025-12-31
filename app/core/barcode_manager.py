from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import cv2
from barcode import get_barcode_class
from barcode.writer import ImageWriter
from PIL import Image
from pyzbar.pyzbar import decode as pyzbar_decode

# zxingcpp is an optional dependency used for barcode decoding.
# Ensure the name is always defined so checks like "if zxingcpp is None"
# do not raise NameError when the import fails.
try:  # pragma: no cover - optional dependency
    import zxingcpp  # type: ignore[import]
except Exception:  # pragma: no cover - missing zxing-cpp is acceptable
    zxingcpp = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class BarcodeGenerator:
    """
    Simple wrapper around python-barcode for generating PNG barcode images.

    The generator will choose EAN-13 for 12/13-digit numeric codes and
    fall back to Code128 for all other inputs.
    """

    def generate(self, code: str, save_path: str) -> str:
        """
        Generate a barcode image for *code* and save it as a PNG file.

        :param code: The data to encode.
        :param save_path: Target path for the PNG file. The directory is
                          created if necessary. If an extension is provided,
                          it will be stripped and replaced with ``.png`` by
                          python-barcode.
        :return: Absolute path to the generated PNG file.
        """
        if not code:
            raise ValueError("Barcode data must not be empty.")

        target_dir = os.path.dirname(os.path.abspath(save_path)) or "."
        os.makedirs(target_dir, exist_ok=True)

        root, _ext = os.path.splitext(os.path.abspath(save_path))

        # Decide barcode symbology
        barcode_name = "code128"
        data = code

        if code.isdigit() and len(code) in (12, 13):
            barcode_name = "ean13"
            # python-barcode expects 12 digits and will compute the checksum
            if len(code) == 13:
                data = code[:-1]

        logger.debug("Generating %s barcode for data=%r at %s", barcode_name, data, root)

        barcode_cls = get_barcode_class(barcode_name)
        barcode_obj = barcode_cls(data, writer=ImageWriter())

        # python-barcode appends the extension automatically
        output = barcode_obj.save(root)
        output_path = os.path.abspath(output)
        logger.info("Barcode image generated at %s", output_path)
        return output_path


class BarcodeScanner:
    """
    Barcode decoding utilities based on OpenCV frames and static images.

    Triple-layer strategy for robustness in the Iranian market:

      1) pyzbar      - fast for most 1D and QR barcodes
      2) zxing-cpp   - robust engine for rotated/difficult codes, PDF417, ITF, etc.
      3) pylibdmtx   - specialized for Data Matrix (e.g., pharmaceuticals)

    All backends are optional; missing libraries are handled gracefully.
    """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def decode_frame(self, frame) -> Optional[str]:
        """
        Decode a barcode from an OpenCV frame (numpy array).

        The method uses a triple-check strategy:
        1) pyzbar       (grayscale)
        2) zxing-cpp    (BGR frame)
        3) pylibdmtx    (grayscale)

        If nothing is found, it retries once on a 90-degree rotated frame.

        :param frame: BGR image as returned by ``cv2.VideoCapture.read()``.
        :return: Decoded barcode string, or ``None`` if nothing was found.
        """
        if frame is None:
            return None

        try:
            # First pass: original orientation
            result = self._decode_frame_with_engines(frame)
            if result:
                return result

            # Optional rotation pass: some 1D barcodes are scanned vertically.
            try:
                rotated = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            except Exception:
                rotated = None

            if rotated is not None:
                return self._decode_frame_with_engines(rotated)

            return None
        except Exception as exc:
            logger.exception("Error decoding barcode from frame: %s", exc)
            return None

    def decode_image(self, image_path: str) -> Optional[str]:
        """
        Decode a barcode from a static image file using the same triple-check
        strategy as decode_frame.

        :param image_path: Path to an image file.
        :return: Decoded barcode string, or ``None`` if nothing was found.
        """
        try:
            if not image_path or not os.path.exists(image_path):
                logger.warning("decode_image called with missing file: %r", image_path)
                return None

            with Image.open(image_path) as img:
                img = img.convert("RGB")
                return self._decode_image_with_engines(img)
        except Exception as exc:
            logger.exception("Error decoding barcode from image %r: %s", image_path, exc)
            return None

    # ------------------------------------------------------------------ #
    # Internal helpers for frames
    # ------------------------------------------------------------------ #
    def _decode_frame_with_engines(self, frame_bgr) -> Optional[str]:
        """
        Run all decoding backends for a single orientation of an OpenCV BGR frame.
        """
        gray = None

        # Layer 1: pyzbar (grayscale)
        try:
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        except Exception:
            gray = None

        if gray is not None:
            result = self._decode_with_pyzbar(gray)
            if result:
                return result

        # Layer 2: zxing-cpp (can work directly on numpy arrays)
        result = self._decode_with_zxingcpp(frame_bgr)
        if result:
            return result

        # Layer 3: pylibdmtx (Data Matrix) using grayscale
        if gray is None:
            try:
                gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            except Exception:
                gray = None

        if gray is not None:
            return self._decode_with_datamatrix(gray)

        return None

    # ------------------------------------------------------------------ #
    # Internal helpers for images (PIL)
    # ------------------------------------------------------------------ #
    def _decode_image_with_engines(self, pil_image: Image.Image) -> Optional[str]:
        """
        Triple-check decoding on a PIL RGB image.
        """
        # Prepare grayscale once
        gray = pil_image.convert("L")

        # Layer 1: pyzbar
        result = self._decode_with_pyzbar(gray)
        if result:
            return result

        # Layer 2: zxing-cpp (works with numpy arrays)
        try:
            import numpy as np  # lazy import to avoid hard dependency at module import time

            bgr = cv2.cvtColor(
                cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2BGR
            )
        except Exception:
            bgr = None

        if bgr is not None:
            result = self._decode_with_zxingcpp(bgr)
            if result:
                return result

        # Layer 3: pylibdmtx (Data Matrix)
        result = self._decode_with_datamatrix(gray)
        if result:
            return result

        # Optional rotation retry (90 degrees)
        try:
            rotated = pil_image.rotate(90, expand=True)
        except Exception:
            rotated = None

        if rotated is not None:
            gray_rot = rotated.convert("L")
            result = self._decode_with_pyzbar(gray_rot)
            if result:
                return result

            result = self._decode_with_datamatrix(gray_rot)
            if result:
                return result

        return None

    # ------------------------------------------------------------------ #
    # Backend-specific helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode_with_pyzbar(image) -> Optional[str]:
        barcodes = pyzbar_decode(image)
        for barcode in barcodes:
            try:
                data = barcode.data.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue
            if data:
                logger.debug(
                    "Decoded barcode (pyzbar) type=%s data=%r",
                    getattr(barcode, "type", "?"),
                    data,
                )
                return data
        return None

    @staticmethod
    def _decode_with_datamatrix(image) -> Optional[str]:
        """
        Attempt to decode Data Matrix codes using pylibdmtx, if installed.
        Accepts either a PIL Image or a numpy array (OpenCV frame).
        """
        try:
            from pylibdmtx.pylibdmtx import decode as decode_datamatrix  # type: ignore[import]
        except Exception:
            return None

        try:
            if isinstance(image, Image.Image):
                pil_img = image.convert("L")
            else:
                # Assume numpy array, convert BGR/gray to grayscale PIL image
                import numpy as np  # lazy import

                if isinstance(image, np.ndarray):
                    if len(image.shape) == 3:
                        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    else:
                        gray = image
                    pil_img = Image.fromarray(gray)
                else:
                    return None

            results = decode_datamatrix(pil_img)
        except Exception as exc:
            logger.exception("Error in pylibdmtx decode_datamatrix: %s", exc)
            return None

        if not results:
            return None

        for res in results:
            try:
                data = res.data.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue
            if data:
                logger.debug("Decoded Data Matrix (pylibdmtx) data=%r", data)
                return data

        return None

    @staticmethod
    def _decode_with_zxingcpp(image) -> Optional[str]:
        """
        Decode using zxing-cpp, if installed.

        Accepts either a numpy array (preferred, e.g., OpenCV frame) or
        a PIL Image.
        """
        if zxingcpp is None:
            return None

        try:
            # zxing-cpp Python binding can handle numpy arrays (BGR/GRAY/RGB)
            # and some PIL images directly.
            results = zxingcpp.read_barcodes(image)
        except Exception as exc:
            logger.exception("Error in zxingcpp.read_barcodes: %s", exc)
            return None

        if not results:
            return None

        for res in results:
            try:
                data = (res.text or "").strip()
            except Exception:
                continue
            if data:
                logger.debug(
                    "Decoded barcode (zxing-cpp) format=%s data=%r",
                    getattr(res, "format", "?"),
                    data,
                )
                return data

        return None