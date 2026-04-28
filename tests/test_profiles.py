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
    resolve_style,
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
    assert profile.end_of_response_sequence == b""
    assert profile.formfeed_on_close is True
    assert profile.instant_output is False
    assert profile.usb_vendor_id is None
    assert profile.usb_product_id is None
    assert profile.columns == 80


# ---------------------------------------------------------------------------
# PrinterProfile capability fields (Phase 21)
# ---------------------------------------------------------------------------


def test_printer_profile_capability_fields_default_to_empty():
    """Phase 21 style capability fields default to empty bytes (capability absent)."""
    profile = PrinterProfile(name="minimal")
    assert profile.bold_on == b""
    assert profile.bold_off == b""
    assert profile.italic_on == b""
    assert profile.italic_off == b""
    assert profile.underline_on == b""
    assert profile.underline_off == b""


def test_printer_profile_buffer_bytes_default_256():
    """Phase 21 buffer_bytes default is 256 (safe value for unknown hardware)."""
    profile = PrinterProfile(name="minimal")
    assert profile.buffer_bytes == 256


def test_printer_profile_capability_fields_are_frozen():
    """The new style fields respect the frozen-dataclass contract."""
    profile = PrinterProfile(name="frozen-test")
    for field_name in (
        "bold_on", "bold_off",
        "italic_on", "italic_off",
        "underline_on", "underline_off",
        "buffer_bytes",
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(profile, field_name, b"\x01")


# ---------------------------------------------------------------------------
# BUILTIN_PROFILES registry
# ---------------------------------------------------------------------------


def test_builtin_profiles_has_ten_entries():
    """BUILTIN_PROFILES has 10 entries: 7 canonical + ibm alias + juki-6100/2200 + juki alias."""
    assert len(BUILTIN_PROFILES) == 10


def test_builtin_profiles_keys():
    """BUILTIN_PROFILES has the expected profile names."""
    expected = {
        "generic", "escp", "ppds", "pcl", "ibm",
        "juki-6100", "juki-2200", "juki",
        "oki-3390",
        "citizen-cts2000",
    }
    assert set(BUILTIN_PROFILES.keys()) == expected


def test_builtin_profiles_have_empty_style_codes_in_phase_21():
    """Phase 21 ships the dataclass shape only; Phase 22 encodes actual style bytes.

    Every built-in MUST have empty bytes for bold/italic/underline in this phase
    — fabricated codes would print garbage on real hardware. This test is a
    regression sentinel: when Phase 22 lands and starts populating codes, this
    test will be updated or removed at that time.
    """
    canonical = (
        "generic", "escp", "ppds", "pcl",
        "juki-6100", "juki-2200",
        "oki-3390", "citizen-cts2000",
    )
    for name in canonical:
        p = BUILTIN_PROFILES[name]
        assert p.bold_on == b"", f"{name} bold_on must be empty in Phase 21"
        assert p.bold_off == b"", f"{name} bold_off must be empty in Phase 21"
        assert p.italic_on == b"", f"{name} italic_on must be empty in Phase 21"
        assert p.italic_off == b"", f"{name} italic_off must be empty in Phase 21"
        assert p.underline_on == b"", f"{name} underline_on must be empty in Phase 21"
        assert p.underline_off == b"", f"{name} underline_off must be empty in Phase 21"


def test_builtin_profiles_have_positive_buffer_bytes():
    """Every built-in exposes a positive buffer_bytes int for Phase 26's chunker."""
    for name, p in BUILTIN_PROFILES.items():
        assert isinstance(p.buffer_bytes, int), f"{name} buffer_bytes must be int"
        assert p.buffer_bytes > 0, f"{name} buffer_bytes must be positive"


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


def test_citizen_cts2000_profile_escpos_defaults():
    """citizen-cts2000 ships with ESC/POS init, LF-only newlines, feed+cut per response."""
    p = BUILTIN_PROFILES["citizen-cts2000"]
    assert p.name == "citizen-cts2000"
    assert p.init_sequence == b"\x1b@"                          # ESC @ — initialize
    assert p.reset_sequence == b"\x1b@"                         # ESC @ — re-init on close
    assert p.end_of_response_sequence == b"\x1bd\x05\x1dV\x00"  # ESC d 5 + GS V 0
    assert p.line_spacing == b""                                # use printer default
    assert p.char_pitch == b""                                  # use printer default
    assert p.crlf is False                                      # ESC/POS uses LF only
    assert p.formfeed_on_close is False                         # receipt printers ignore \f
    assert p.instant_output is True                             # thermal: skip per-char pacing
    assert p.usb_vendor_id == 0x2730                            # CITIZEN (live ioreg VID)
    assert p.usb_product_id == 0x2002                           # CT-S2000 PID
    assert p.columns == 42                                      # Font A on 80mm thermal paper


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
                    "end_of_response_sequence": "1b64051d5600",
                    "formfeed_on_close": False,
                    "instant_output": True,
                    "usb_vendor_id": "04b8",
                    "usb_product_id": "0202",
                    "columns": 132,
                    "bold_on": "1b45",
                    "bold_off": "1b46",
                    "italic_on": "1b34",
                    "italic_off": "1b35",
                    "underline_on": "1b2d01",
                    "underline_off": "1b2d00",
                    "buffer_bytes": 64,
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
    assert p.end_of_response_sequence == b"\x1bd\x05\x1dV\x00"
    assert p.formfeed_on_close is False
    assert p.instant_output is True
    assert p.usb_vendor_id == 0x04B8
    assert p.usb_product_id == 0x0202
    assert p.columns == 132
    assert p.bold_on == b"\x1bE"
    assert p.bold_off == b"\x1bF"
    assert p.italic_on == b"\x1b4"
    assert p.italic_off == b"\x1b5"
    assert p.underline_on == b"\x1b-\x01"
    assert p.underline_off == b"\x1b-\x00"
    assert p.buffer_bytes == 64


def test_load_custom_profiles_style_hex_round_trip():
    """Phase 21 style capability hex strings decode to bytes via bytes.fromhex."""
    raw = {
        "printer": {
            "profiles": {
                "styled": {
                    "bold_on": "1b45",       # ESC E
                    "bold_off": "1b46",      # ESC F
                    "italic_on": "1b34",     # ESC 4
                    "italic_off": "1b35",    # ESC 5
                    "underline_on": "1b2d01",   # ESC - 1
                    "underline_off": "1b2d00",  # ESC - 0
                }
            }
        }
    }
    result = load_custom_profiles(raw)
    p = result["styled"]
    assert p.bold_on == b"\x1bE"
    assert p.bold_off == b"\x1bF"
    assert p.italic_on == b"\x1b4"
    assert p.italic_off == b"\x1b5"
    assert p.underline_on == b"\x1b-\x01"
    assert p.underline_off == b"\x1b-\x00"


def test_load_custom_profiles_buffer_bytes_int():
    """buffer_bytes is read as a plain integer (NOT a hex string)."""
    raw = {
        "printer": {
            "profiles": {
                "chunked": {
                    "buffer_bytes": 128,
                }
            }
        }
    }
    result = load_custom_profiles(raw)
    assert result["chunked"].buffer_bytes == 128


def test_load_custom_profiles_buffer_bytes_default_256_when_absent():
    """Missing buffer_bytes defaults to 256."""
    raw = {
        "printer": {
            "profiles": {
                "bare": {}
            }
        }
    }
    result = load_custom_profiles(raw)
    assert result["bare"].buffer_bytes == 256


def test_load_custom_profiles_style_keys_default_empty_when_absent():
    """All six style keys default to empty bytes when absent from TOML."""
    raw = {
        "printer": {
            "profiles": {
                "bare": {}
            }
        }
    }
    result = load_custom_profiles(raw)
    p = result["bare"]
    assert p.bold_on == b""
    assert p.bold_off == b""
    assert p.italic_on == b""
    assert p.italic_off == b""
    assert p.underline_on == b""
    assert p.underline_off == b""


# ---------------------------------------------------------------------------
# resolve_style() fallback chain (CAP-03)
# ---------------------------------------------------------------------------


class TestResolveStyle:
    """Cover the documented italic→underline→plain and bold→underline→plain chains."""

    # Realistic Epson ESC/P bytes used as fixture data — phase 22 will encode
    # these into actual built-ins. Using them here makes the tests read like
    # real-world calls.
    BOLD_ON = b"\x1bE"
    BOLD_OFF = b"\x1bF"
    ITALIC_ON = b"\x1b4"
    ITALIC_OFF = b"\x1b5"
    UNDERLINE_ON = b"\x1b-\x01"
    UNDERLINE_OFF = b"\x1b-\x00"

    def _profile(self, **kwargs) -> PrinterProfile:
        """Build a minimal PrinterProfile overriding only the fields under test."""
        return PrinterProfile(name="fixture", **kwargs)

    # --- italic chain ---

    def test_italic_returns_italic_codes_when_set(self):
        p = self._profile(italic_on=self.ITALIC_ON, italic_off=self.ITALIC_OFF)
        assert resolve_style(p, "italic") == (self.ITALIC_ON, self.ITALIC_OFF)

    def test_italic_falls_back_to_underline_when_italic_empty(self):
        p = self._profile(
            underline_on=self.UNDERLINE_ON, underline_off=self.UNDERLINE_OFF,
        )
        assert resolve_style(p, "italic") == (self.UNDERLINE_ON, self.UNDERLINE_OFF)

    def test_italic_returns_plain_when_italic_and_underline_both_empty(self):
        p = self._profile()
        assert resolve_style(p, "italic") == (b"", b"")

    def test_italic_wins_over_underline_when_both_set(self):
        p = self._profile(
            italic_on=self.ITALIC_ON, italic_off=self.ITALIC_OFF,
            underline_on=self.UNDERLINE_ON, underline_off=self.UNDERLINE_OFF,
        )
        assert resolve_style(p, "italic") == (self.ITALIC_ON, self.ITALIC_OFF)

    # --- bold chain ---

    def test_bold_returns_bold_codes_when_set(self):
        p = self._profile(bold_on=self.BOLD_ON, bold_off=self.BOLD_OFF)
        assert resolve_style(p, "bold") == (self.BOLD_ON, self.BOLD_OFF)

    def test_bold_falls_back_to_underline_when_bold_empty(self):
        p = self._profile(
            underline_on=self.UNDERLINE_ON, underline_off=self.UNDERLINE_OFF,
        )
        assert resolve_style(p, "bold") == (self.UNDERLINE_ON, self.UNDERLINE_OFF)

    def test_bold_returns_plain_when_bold_and_underline_both_empty(self):
        p = self._profile()
        assert resolve_style(p, "bold") == (b"", b"")

    def test_bold_wins_over_underline_when_both_set(self):
        p = self._profile(
            bold_on=self.BOLD_ON, bold_off=self.BOLD_OFF,
            underline_on=self.UNDERLINE_ON, underline_off=self.UNDERLINE_OFF,
        )
        assert resolve_style(p, "bold") == (self.BOLD_ON, self.BOLD_OFF)

    # --- underline chain (terminal node, no further fallback) ---

    def test_underline_returns_underline_codes_when_set(self):
        p = self._profile(
            underline_on=self.UNDERLINE_ON, underline_off=self.UNDERLINE_OFF,
        )
        assert resolve_style(p, "underline") == (self.UNDERLINE_ON, self.UNDERLINE_OFF)

    def test_underline_returns_plain_when_underline_empty(self):
        p = self._profile()
        assert resolve_style(p, "underline") == (b"", b"")

    def test_underline_does_not_fall_back_to_bold_or_italic(self):
        """Underline is the terminal node — bold/italic codes do NOT substitute for it."""
        p = self._profile(
            bold_on=self.BOLD_ON, bold_off=self.BOLD_OFF,
            italic_on=self.ITALIC_ON, italic_off=self.ITALIC_OFF,
        )
        assert resolve_style(p, "underline") == (b"", b"")

    # --- error handling ---

    def test_unknown_style_raises_valueerror(self):
        p = self._profile()
        with pytest.raises(ValueError, match="Unknown style"):
            resolve_style(p, "strikethrough")

    def test_unknown_style_message_lists_valid_styles(self):
        p = self._profile()
        with pytest.raises(ValueError, match="bold.*italic.*underline|italic.*underline|bold"):
            resolve_style(p, "blink")


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
