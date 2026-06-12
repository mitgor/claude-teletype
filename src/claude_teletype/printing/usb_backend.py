"""Frozen-mode libusb backend seam for pyusb (R027).

When running from a PyInstaller bundle (``sys.frozen``), pyusb's default
backend discovery (ctypes.util.find_library) cannot see the bundled
libusb-1.0.dylib, so we build an explicit libusb1 backend pointed at the
dylib shipped inside the bundle (``sys._MEIPASS``). In dev mode this module
is a no-op: ``get_frozen_backend()`` returns None and ``backend=None`` to
``usb.core.find()`` is identical to today's default discovery.

If the bundled dylib is missing or unloadable we also return None, so the
existing ``NoBackendError`` → CUPS/simulator fallback paths fire unchanged
(R029).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def get_frozen_backend() -> Any | None:
    """Return an explicit libusb1 backend for frozen builds, else None.

    Returns None when:
    - not frozen (dev install — default pyusb backend discovery applies),
    - the bundled libusb-1.0.dylib is absent from sys._MEIPASS,
    - usb.backend.libusb1.get_backend() cannot load the dylib.

    Passing the resulting None as ``backend=`` to ``usb.core.find()`` keeps
    pyusb's default behavior, so dev mode is untouched.
    """
    if not getattr(sys, "frozen", False):
        return None

    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None

    lib = Path(meipass) / "libusb-1.0.dylib"
    if not lib.exists():
        return None

    # Function-local import: pyusb is an optional extra (MEM013 idiom).
    import usb.backend.libusb1

    return usb.backend.libusb1.get_backend(find_library=lambda name: str(lib))
