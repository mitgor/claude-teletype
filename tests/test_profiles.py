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


def _make_usb_device(vid: int, pid: int, interface_class: int = 7) -> MagicMock:
    """Create a mock USB device with proper iteration support for pyusb-style enumeration."""
    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = interface_class

    mock_cfg = MagicMock()
    # Make configuration iterable over interfaces
    mock_cfg.__iter__ = lambda self: iter([mock_intf])

    mock_dev = MagicMock()
    mock_dev.idVendor = vid
    mock_dev.idProduct = pid
    # Make device iterable over configurations
    mock_dev.__iter__ = lambda self: iter([mock_cfg])

    return mock_dev


def _patch_usb(mock_usb_core):
    """Create a sys.modules patch dict where usb.core resolves correctly.

    Python's import of 'usb.core' first gets sys.modules['usb'], then
    accesses .core on it. With a plain MagicMock for 'usb', the .core
    attribute is an auto-generated MagicMock, not our mock_usb_core.
    Fix: set mock_usb.core = mock_usb_core explicitly.
    """
    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    return {"usb": mock_usb, "usb.core": mock_usb_core}


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


def test_builtin_profiles_has_nine_entries():
    """BUILTIN_PROFILES has 9 entries: 6 canonical + ibm alias + juki-6100/2200 + juki alias."""
    assert len(BUILTIN_PROFILES) == 9


def test_builtin_profiles_keys():
    """BUILTIN_PROFILES has the expected profile names."""
    expected = {
        "generic", "escp", "ppds", "pcl", "ibm",
        "juki-6100", "juki-2200", "juki",
        "oki-3390",
    }
    assert set(BUILTIN_PROFILES.keys()) == expected


def test_oki_3390_profile_epson_fx2_defaults():
    """oki-3390 ships with Epson FX-2 ESC sequences and OKI USB VID."""
    p = BUILTIN_PROFILES["oki-3390"]
    assert p.name == "oki-3390"
    assert p.init_sequence == b"\x1b@"          # ESC @ — Epson init
    assert p.reset_sequence == b"\x1b@"
    assert p.line_spacing == b"\x1b\x32"         # ESC 2 — 6 LPI
    assert p.char_pitch == b"\x1bP"              # ESC P — 10 CPI
    assert p.crlf is False                       # ESC/P uses LF only
    assert p.formfeed_on_close is True
    assert p.usb_vendor_id == 0x06BC             # OKI Data Corp
    assert p.usb_product_id is None              # VID-only auto-detect
    assert p.columns == 80


def test_juki_2200_profile_typewriter_defaults():
    """juki-2200 is a plain-ASCII typewriter: no ESC codes, CR+LF, no formfeed."""
    p = BUILTIN_PROFILES["juki-2200"]
    assert p.name == "juki-2200"
    assert p.init_sequence == b""
    assert p.reset_sequence == b""
    assert p.crlf is True
    assert p.reinit_on_newline is False
    assert p.formfeed_on_close is False
    assert p.usb_vendor_id is None  # shares CH341 adapter with 6100; pick explicitly


def test_juki_alias_resolves_to_6100():
    """`get_profile("juki")` keeps working as a backward-compat alias for juki-6100."""
    juki = get_profile("juki")
    six = get_profile("juki-6100")
    assert juki.init_sequence == six.init_sequence
    assert juki.reinit_sequence == six.reinit_sequence
    assert juki.usb_vendor_id == six.usb_vendor_id
    assert juki.usb_product_id == six.usb_product_id


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
    with patch.dict("sys.modules", _patch_usb(mock_usb_core)):
        result = auto_detect_profile()
        assert result is None


def test_auto_detect_profile_matching_vid_pid():
    """auto_detect_profile returns matching profile for known VID:PID."""
    mock_dev = _make_usb_device(vid=0x04B8, pid=0x0005)  # Epson printer

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", _patch_usb(mock_usb_core)):
        result = auto_detect_profile()
        assert result is not None
        assert result.name == "escp"


def test_auto_detect_profile_no_matching_device():
    """auto_detect_profile returns None when no device matches."""
    mock_dev = _make_usb_device(vid=0x1234, pid=0x5678)  # Unknown vendor

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", _patch_usb(mock_usb_core)):
        result = auto_detect_profile()
        assert result is None


def test_auto_detect_profile_vid_only_match():
    """auto_detect_profile matches VID-only when profile has no PID."""
    # HP profile has VID 0x03F0 but no PID
    mock_dev = _make_usb_device(vid=0x03F0, pid=0x9999)  # Any HP product

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", _patch_usb(mock_usb_core)):
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

    mock_dev = _make_usb_device(vid=0x04B8, pid=0x0005)

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", _patch_usb(mock_usb_core)):
        result = auto_detect_profile(extra_profiles=extra)
        assert result is not None
        assert result.name == "epson-exact"


def test_auto_detect_profile_skips_non_printer_class():
    """auto_detect_profile ignores USB devices that are not printer class 7."""
    mock_dev = _make_usb_device(vid=0x04B8, pid=0x0005, interface_class=3)  # HID, not printer

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = [mock_dev]

    with patch.dict("sys.modules", _patch_usb(mock_usb_core)):
        result = auto_detect_profile()
        assert result is None


# ---------------------------------------------------------------------------
# IBM alias
# ---------------------------------------------------------------------------


def test_ibm_alias_resolves_to_ppds_sequences():
    """get_profile('ibm') returns a profile with the same ESC sequences as ppds but name='ibm'."""
    ibm = get_profile("ibm")
    ppds = get_profile("ppds")
    assert ibm.name == "ibm"
    assert ibm.init_sequence == ppds.init_sequence
    assert ibm.reset_sequence == ppds.reset_sequence
    assert ibm.line_spacing == ppds.line_spacing
    assert ibm.char_pitch == ppds.char_pitch


def test_ibm_alias_case_insensitive():
    """get_profile('IBM') works (case-insensitive lookup)."""
    profile = get_profile("IBM")
    assert profile.name == "ibm"


def test_ibm_profile_in_available_list():
    """'ibm' appears in the 'Available:' message when an unknown profile is requested."""
    with pytest.raises(ValueError, match="ibm"):
        get_profile("nonexistent")
