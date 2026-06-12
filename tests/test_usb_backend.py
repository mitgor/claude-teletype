"""Tests for the frozen-mode libusb backend seam (R027/R029).

Covers usb_backend.get_frozen_backend() in dev and frozen modes, the
backend= threading through discovery's usb.core.find() sites, and the
frozen-aware NoBackendError diagnostics. No real USB hardware required.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from claude_teletype.printing.discovery import (
    discover_all,
    discover_usb_device_verbose,
)
from claude_teletype.printing.usb_backend import get_frozen_backend

# ---------------------------------------------------------------------------
# get_frozen_backend()
# ---------------------------------------------------------------------------


def test_not_frozen_returns_none():
    """Dev mode (sys.frozen unset/falsy) -> None, default pyusb discovery."""
    assert get_frozen_backend() is None


def test_not_frozen_explicit_false(monkeypatch):
    monkeypatch.setattr("sys.frozen", False, raising=False)
    assert get_frozen_backend() is None


def test_frozen_with_bundled_dylib_builds_explicit_backend(monkeypatch, tmp_path):
    """Frozen + dylib present -> libusb1.get_backend with find_library
    resolving to the bundled path."""
    dylib = tmp_path / "libusb-1.0.dylib"
    dylib.touch()
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)

    import usb.backend.libusb1

    sentinel_backend = object()
    captured: dict = {}

    def fake_get_backend(find_library=None):
        captured["find_library"] = find_library
        return sentinel_backend

    monkeypatch.setattr(usb.backend.libusb1, "get_backend", fake_get_backend)

    result = get_frozen_backend()

    assert result is sentinel_backend
    assert captured["find_library"]("libusb-1.0") == str(dylib)


def test_frozen_without_dylib_returns_none(monkeypatch, tmp_path):
    """Frozen but dylib absent -> None, so NoBackendError handlers fire."""
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    assert get_frozen_backend() is None


def test_frozen_without_meipass_returns_none(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.delattr("sys._MEIPASS", raising=False)
    assert get_frozen_backend() is None


def test_frozen_get_backend_returning_none_propagates(monkeypatch, tmp_path):
    """libusb1.get_backend failing to load the dylib -> None (R029)."""
    (tmp_path / "libusb-1.0.dylib").touch()
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)

    import usb.backend.libusb1

    monkeypatch.setattr(usb.backend.libusb1, "get_backend", lambda find_library=None: None)
    assert get_frozen_backend() is None


# ---------------------------------------------------------------------------
# backend= threading through discovery
# ---------------------------------------------------------------------------


def _mock_usb_modules():
    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_util = MagicMock()
    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util
    return mock_usb, mock_usb_core, mock_usb_util


@contextmanager
def _discover_all_env(mock_usb, mock_usb_core, mock_usb_util):
    """Mocked-pyusb environment for discover_all().

    discover_all() pre-checks importlib.util.find_spec("usb"), which returns
    None for a MagicMock in sys.modules, so find_spec is patched to report
    pyusb as installed (same convention as test_diagnose.py). CUPS discovery
    is stubbed out to keep the test hermetic.
    """
    import importlib.util

    original_find_spec = importlib.util.find_spec

    def patched_find_spec(name, *args, **kwargs):
        if name == "usb":
            return MagicMock()
        return original_find_spec(name, *args, **kwargs)

    with patch("importlib.util.find_spec", side_effect=patched_find_spec):
        with patch.dict(
            "sys.modules",
            {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util},
        ):
            with patch(
                "claude_teletype.printing.discovery.discover_cups_printers",
                return_value=[],
            ):
                yield


def test_find_receives_backend_kwarg_in_dev_mode():
    """Dev mode: find(find_all=True, backend=None) — behavior unchanged."""
    mock_usb, mock_usb_core, mock_usb_util = _mock_usb_modules()
    mock_usb_core.find.return_value = []

    with patch.dict(
        "sys.modules",
        {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util},
    ):
        driver, diagnostics = discover_usb_device_verbose()

    assert driver is None
    mock_usb_core.find.assert_called_once_with(find_all=True, backend=None)
    assert any("No USB printer-class devices found" in d for d in diagnostics)


def test_discover_all_find_receives_backend_kwarg():
    mock_usb, mock_usb_core, mock_usb_util = _mock_usb_modules()
    mock_usb_core.find.return_value = []

    with _discover_all_env(mock_usb, mock_usb_core, mock_usb_util):
        result = discover_all()

    assert result.libusb_available is True
    mock_usb_core.find.assert_called_once_with(find_all=True, backend=None)


def test_kernel_driver_probe_passes_backend(monkeypatch):
    from claude_teletype.printing.discovery import kernel_driver_holds_printer

    mock_usb, mock_usb_core, mock_usb_util = _mock_usb_modules()
    mock_usb_core.find.return_value = None

    with patch.dict(
        "sys.modules",
        {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util},
    ):
        held = kernel_driver_holds_printer(0x04B8, 0x0202)

    assert held is False
    mock_usb_core.find.assert_called_once_with(
        idVendor=0x04B8, idProduct=0x0202, backend=None
    )


# ---------------------------------------------------------------------------
# Frozen-aware NoBackendError diagnostics
# ---------------------------------------------------------------------------

FROZEN_MSG = "bundled libusb-1.0.dylib missing or unloadable"
DEV_MSG = "brew install libusb"


def test_verbose_discovery_diagnostic_dev_mode():
    """Non-frozen NoBackendError keeps the brew install hint."""
    mock_usb, mock_usb_core, mock_usb_util = _mock_usb_modules()
    mock_usb_core.find.side_effect = mock_usb_core.NoBackendError("no backend")

    with patch.dict(
        "sys.modules",
        {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util},
    ):
        driver, diagnostics = discover_usb_device_verbose()

    assert driver is None
    assert any(DEV_MSG in d for d in diagnostics)
    assert not any(FROZEN_MSG in d for d in diagnostics)


def test_verbose_discovery_diagnostic_frozen(monkeypatch):
    """Frozen NoBackendError must NOT tell the user to brew install."""
    monkeypatch.setattr("sys.frozen", True, raising=False)
    mock_usb, mock_usb_core, mock_usb_util = _mock_usb_modules()
    mock_usb_core.find.side_effect = mock_usb_core.NoBackendError("no backend")

    with patch.dict(
        "sys.modules",
        {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util},
    ):
        driver, diagnostics = discover_usb_device_verbose()

    assert driver is None
    assert any(FROZEN_MSG in d for d in diagnostics)
    assert any("Falling back to CUPS/simulator" in d for d in diagnostics)
    assert not any(DEV_MSG in d for d in diagnostics)


def test_discover_all_diagnostic_dev_mode():
    mock_usb, mock_usb_core, mock_usb_util = _mock_usb_modules()
    mock_usb_core.find.side_effect = mock_usb_core.NoBackendError("no backend")

    with _discover_all_env(mock_usb, mock_usb_core, mock_usb_util):
        result = discover_all()

    assert result.libusb_available is False
    assert any(DEV_MSG in d for d in result.diagnostics)
    assert not any(FROZEN_MSG in d for d in result.diagnostics)


def test_discover_all_diagnostic_frozen(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    mock_usb, mock_usb_core, mock_usb_util = _mock_usb_modules()
    mock_usb_core.find.side_effect = mock_usb_core.NoBackendError("no backend")

    with _discover_all_env(mock_usb, mock_usb_core, mock_usb_util):
        result = discover_all()

    assert result.libusb_available is False
    assert any(FROZEN_MSG in d for d in result.diagnostics)
    assert not any(DEV_MSG in d for d in result.diagnostics)
