from __future__ import annotations

from pathlib import Path
import sys
from typing import Union


PathLike = Union[str, Path]


def resource_path(relative_path: PathLike) -> Path:
    """Return an absolute path to *relative_path* that works both
    during development and when the application is bundled with
    PyInstaller.

    The function prefers the temporary extraction directory used by
    PyInstaller (``sys._MEIPASS``). When not running from a bundled
    executable it resolves the path relative to the project root
    (two levels above this file, i.e. the directory that contains
    ``app/``).
    """
    # PyInstaller onefile/onedir runtime hook
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        base_path = Path(base)
    else:
        # app/utils.py -> app/ -> project root
        base_path = Path(__file__).resolve().parent.parent

    return base_path / Path(relative_path)
