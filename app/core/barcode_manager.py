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

try:
    from pylibdmtx.pylibdmtx import decode as decode_datamatrix
except Exception:  # pragma: no cover - optional dependency
    decode_datamatrix = None

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

    Supports both 1D/QR barcodes (via pyzbar) and Data Matrix codes
    (via pylibdmtx when available).
    """

    def decode_frame(self, frame) -> Optional[str]:
        """
        Decode a barcode from an OpenCV frame (numpy array).

        :param frame: BGR image as returned by ``cv2.VideoCapture.read()``.
        :return: Decoded barcode string, or ``None`` if nothing was found.
        """
        if frame is None:
            return None

        try:
            # Prefer pyzbar on a grayscale view of the frame for robustness.
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            result = self._decode_with_pyzbar(gray)
            if result:
                return result

            # Fallback: try Data Matrix decoding with pylibdmtx, if available.
            return self._decode_with_datamatrix(gray)
        except Exception as exc:
            logger.exception("Error decoding barcode from frame: %s", exc)
            return None

    def decode_image(self, image_path: str) -> Optional[str]:
        """
        Decode a barcode from a static image file.

        :param image_path: Path to an image file.
        :return: Decoded barcode string, or ``None`` if nothing was found.
        """
        try:
            if not image_path or not os.path.exists(image_path):
                logger.warning("decode_image called with missing file: %r", image_path)
                return None

            with Image.open(image_path) as img:
                img = img.convert("RGB")
                result = self._decode_with_pyzbar(img)
                if result:
                    return result

                gray = img.convert("L")
                result = self._decode_with_pyzbar(gray)
                if result:
                    return result

            # Fallback to Data Matrix decoding using pylibdmtx if pyzbar failed.
            with Image.open(image_path) as img2:
                img2 = img2.convert("L")
                return self._decode_with_datamatrix(img2)
        except Exception as exc:
            logger.exception("Error decoding barcode from image %r: %s", image_path, exc)
            return None

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
        if decode_datamatrix is None:
            return None

        try:
            if isinstance(image, Image.Image):
                pil_img = image.convert("L")
            else:
                # Assume numpy array, convert BGR/gray to grayscale PIL image
                if len(image.shape) == 3:
                    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                else:
                    gray = image
                pil_img = Image.fromarray(gray)

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