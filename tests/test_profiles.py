"""Tests for printer profile dataclass, registry, custom loading, and auto-detection."""

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch

import pytest

from claude_teletype.profiles import (
    BUILTIN_PROFILES,
    PrinterProfile,
    auto_detect_profile,
    get_profile,
    load_custom_profiles,
)


# ---------------------------------------------------------------------------
# PrinterProfile dataclass
# ---------------------------------------------------------------------------


def test_printer_profile_is_frozen():
    """PrinterProfile instances are immutable (frozen dataclass)."""
    profile = PrinterProfile(name="test")
    with pytest.raises(FrozenInstanceError):
        profile.name = "mutated"


def test_printer_profile_defaults():
    """PrinterProfile has sensible defaults for all optional fields."""
    profile = PrinterProfile(name="minimal")
    assert profile.name == "minimal"
    assert profile.description == ""
    assert profile.init_sequence == b""
    assert profile.reset_sequence == b""
    assert profile.line_spacing == b""
    assert profile.char_pitch == b""
    assert profile.crlf is False
    assert profile.reinit_on_newline is False
    assert profile.reinit_sequence == b""
    assert profile.formfeed_on_close is True
    assert profile.usb_vendor_id is None
    assert profile.usb_product_id is None
    assert profile.columns == 80


# ---------------------------------------------------------------------------
# BUILTIN_PROFILES registry
# ---------------------------------------------------------------------------


def test_builtin_profiles_has_five_entries():
    """BUILTIN_PROFILES contains exactly 5 profiles."""
    assert len(BUILTIN_PROFILES) == 5


def test_builtin_profiles_keys():
    """BUILTIN_PROFILES has the expected profile names."""
    expected = {"generic", "juki", "escp", "ppds", "pcl"}
    assert set(BUILTIN_PROFILES.keys()) == expected


def test_generic_profile_no_esc_codes():
    """Generic profile has empty bytes and LF-only."""
    p = BUILTIN_PROFILES["generic"]
    assert p.name == "generic"
    assert p.init_sequence == b""
    assert p.reset_sequence == b""
    assert p.line_spacing == b""
    assert p.char_pitch == b""
    assert p.crlf is False


def test_juki_profile_esc_sequences():
    """Juki profile has correct ESC SUB I init and CR+LF newline."""
    p = BUILTIN_PROFILES["juki"]
    assert p.name == "juki"
    assert p.init_sequence == b"\x1b\x1aI"          # ESC SUB I
    assert p.line_spacing == b"\x1b\x1e\x09"         # ESC RS 9
    assert p.char_pitch == b"\x1bQ"                   # ESC Q
    assert p.crlf is True
    assert p.reinit_on_newline is True
    assert p.reinit_sequence == b"\x1b\x1e\x09\x1bQ"  # LINE_SPACING + FIXED_PITCH
    assert p.formfeed_on_close is True


def test_escp_profile_esc_sequences():
    """Epson ESC/P profile has correct ESC @ init and USB VID."""
    p = BUILTIN_PROFILES["escp"]
    assert p.name == "escp"
    assert p.init_sequence == b"\x1b@"               # ESC @
    assert p.reset_sequence == b"\x1b@"              # ESC @
    assert p.line_spacing == b"\x1b\x32"             # ESC 2
    assert p.char_pitch == b"\x1bP"                  # ESC P
    assert p.crlf is False
    assert p.usb_vendor_id == 0x04B8                 # Seiko Epson Corp


def test_ppds_profile_esc_sequences():
    """IBM PPDS profile has correct ESC @ init and DC2 pitch."""
    p = BUILTIN_PROFILES["ppds"]
    assert p.name == "ppds"
    assert p.init_sequence == b"\x1b@"
    assert p.reset_sequence == b"\x1b@"
    assert p.line_spacing == b"\x1b\x32"
    assert p.char_pitch == b"\x12"                   # DC2


def test_pcl_profile_esc_sequences():
    """HP PCL5 profile has correct ESC E init and USB VID."""
    p = BUILTIN_PROFILES["pcl"]
    assert p.name == "pcl"
    assert p.init_sequence == b"\x1bE"               # ESC E
    assert p.reset_sequence == b"\x1bE"
    assert p.line_spacing == b"\x1b&l6D"
    assert p.char_pitch == b"\x1b(s10H"
    assert p.usb_vendor_id == 0x03F0                 # HP Inc


# ---------------------------------------------------------------------------
# get_profile()
# ---------------------------------------------------------------------------


def test_get_profile_by_name():
    """get_profile('juki') returns the Juki profile."""
    p = get_profile("juki")
    assert p.name == "juki"
    assert p.init_sequence == b"\x1b\x1aI"


def test_get_profile_case_insensitive():
    """get_profile('JUKI') returns the same as get_profile('juki')."""
    assert get_profile("JUKI") == get_profile("juki")


def test_get_profile_case_insensitive_mixed():
    """get_profile('EscP') returns the ESC/P profile."""
    assert get_profile("EscP") == get_profile("escp")


def test_get_profile_strips_whitespace():
    """get_profile(' juki ') returns the Juki profile."""
    assert get_profile(" juki ") == get_profile("juki")


def test_get_profile_unknown_raises_valueerror():
    """get_profile('nonexistent') raises ValueError listing available names."""
    with pytest.raises(ValueError, match="Unknown printer profile"):
        get_profile("nonexistent")


def test_get_profile_valueerror_lists_available():
    """ValueError message includes available profile names."""
    with pytest.raises(ValueError, match="Available:"):
        get_profile("no-such-profile")


# ---------------------------------------------------------------------------
# load_custom_profiles()
# ---------------------------------------------------------------------------


def test_load_custom_profiles_valid_hex():
    """load_custom_profiles converts hex-encoded init to bytes."""
    raw = {
        "printer": {
            "profiles": {
                "my-printer": {
                    "init": "1b40",
                    "crlf": True,
                }
            }
        }
    }
    result = load_custom_profiles(raw)
    assert "my-printer" in result
    p = result["my-printer"]
    assert p.name == "my-printer"
    assert p.init_sequence == b"\x1b@"
    assert p.crlf is True


def test_load_custom_profiles_usb_vid_hex():
    """USB VID/PID parsed as hex strings."""
    raw = {
        "printer": {
            "profiles": {
                "custom-epson": {
                    "usb_vendor_id": "04b8",
                    "usb_product_id": "0202",
                }
            }
        }
    }
    result = load_custom_profiles(raw)
    p = result["custom-epson"]
    assert p.usb_vendor_id == 0x04B8
    assert p.usb_product_id == 0x0202


def test_load_custom_profiles_empty_dict():
    """Empty dict returns empty dict."""
    assert load_custom_profiles({}) == {}


def test_load_custom_profiles_no_profiles_section():
    """Missing profiles section returns empty dict."""
    raw = {"printer": {"profile": "generic"}}
    assert load_custom_profiles(raw) == {}


def test_load_custom_profiles_missing_optional_fields():
    """Missing optional fields get defaults."""
    raw = {
        "printer": {
            "profiles": {
                "bare": {}
            }
        }
    }
    result = load_custom_profiles(raw)
    p = result["bare"]
    assert p.name == "bare"
    assert p.init_sequence == b""
    assert p.reset_sequence == b""
    assert p.crlf is False
    assert p.formfeed_on_close is True
    assert p.usb_vendor_id is None
    assert p.columns == 80


def test_load_custom_profiles_all_fields():
    """All fields in TOML are correctly parsed."""
    raw = {
        "printer": {
            "profiles": {
                "full": {
                    "description": "Full custom profile",
                    "init": "1b40",
                    "reset": "1b40",
                    "line_spacing": "1b32",
                    "char_pitch": "1b50",
                    "crlf": True,
                    "reinit_on_newline": True,
                    "reinit_sequence": "1b321b50",
                    "formfeed_on_close": False,
                    "usb_vendor_id": "04b8",
                    "usb_product_id": "0202",
                    "columns": 132,
                }
            }
        }
    }
    result = load_custom_profiles(raw)
    p = result["full"]
    assert p.description == "Full custom profile"
    assert p.init_sequence == b"\x1b@"
    assert p.reset_sequence == b"\x1b@"
    assert p.line_spacing == b"\x1b\x32"
    assert p.char_pitch == b"\x1bP"
    assert p.crlf is True
    assert p.reinit_on_newline is True
    assert p.reinit_sequence == b"\x1b\x32\x1bP"
    assert p.formfeed_on_close is False
    assert p.usb_vendor_id == 0x04B8
    assert p.usb_product_id == 0x0202
    assert p.columns == 132


# ---------------------------------------------------------------------------
# auto_detect_profile()
# ---------------------------------------------------------------------------


def test_auto_detect_profile_no_pyusb():
    """auto_detect_profile returns None when pyusb is not available."""
    with patch.dict("sys.modules", {"usb": None, "usb.core": None}):
        result = auto_detect_profile()
        assert result is None


def test_auto_detect_profile_no_backend():
    """auto_detect_profile returns None when no USB backend is available."""
    mock_usb_core = MagicMock()
    mock_usb_core.find.side_effect = Exception("No backend available")
    with patch.dict("sys.modules", {"usb": MagicMock(), "usb.core": mock_usb_core}):
        result = auto_detect_profile()
        assert result is None


def test_auto_detect_profile_matching_vid_pid():
    """auto_detect_profile returns matching profile for known VID:PID."""
    mock_dev = MagicMock()
    mock_dev.idVendor = 0x04B8   # Epson
    mock_dev.idProduct = 0x0005
    # Create mock USB interface with printer class 7
    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 7
    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", {"usb": MagicMock(), "usb.core": mock_usb_core}):
        result = auto_detect_profile()
        assert result is not None
        assert result.name == "escp"


def test_auto_detect_profile_no_matching_device():
    """auto_detect_profile returns None when no device matches."""
    mock_dev = MagicMock()
    mock_dev.idVendor = 0x1234   # Unknown vendor
    mock_dev.idProduct = 0x5678
    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 7
    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", {"usb": MagicMock(), "usb.core": mock_usb_core}):
        result = auto_detect_profile()
        assert result is None


def test_auto_detect_profile_vid_only_match():
    """auto_detect_profile matches VID-only when profile has no PID."""
    # HP profile has VID 0x03F0 but no PID
    mock_dev = MagicMock()
    mock_dev.idVendor = 0x03F0
    mock_dev.idProduct = 0x9999   # Any HP product
    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 7
    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", {"usb": MagicMock(), "usb.core": mock_usb_core}):
        result = auto_detect_profile()
        assert result is not None
        assert result.name == "pcl"


def test_auto_detect_profile_exact_match_priority():
    """Exact VID+PID match takes priority over VID-only match."""
    # Set up: extra_profiles with exact PID match for Epson
    extra = {
        "epson-exact": PrinterProfile(
            name="epson-exact",
            usb_vendor_id=0x04B8,
            usb_product_id=0x0005,
        )
    }

    mock_dev = MagicMock()
    mock_dev.idVendor = 0x04B8
    mock_dev.idProduct = 0x0005
    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 7
    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", {"usb": MagicMock(), "usb.core": mock_usb_core}):
        result = auto_detect_profile(extra_profiles=extra)
        assert result is not None
        assert result.name == "epson-exact"


def test_auto_detect_profile_skips_non_printer_class():
    """auto_detect_profile ignores USB devices that are not printer class 7."""
    mock_dev = MagicMock()
    mock_dev.idVendor = 0x04B8   # Epson vendor but not a printer
    mock_dev.idProduct = 0x0005
    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 3  # HID class, not printer
    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", {"usb": MagicMock(), "usb.core": mock_usb_core}):
        result = auto_detect_profile()
        assert result is None
