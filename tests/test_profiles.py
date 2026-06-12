"""Tests for printer profile dataclass, registry, custom loading, and styles.

USB auto-detection moved to detection.detect_native_profile (T04); its
tests live in tests/test_detection.py.
"""

from dataclasses import FrozenInstanceError

import pytest

from claude_teletype.printing.profiles import (
    BUILTIN_PROFILES,
    PrinterProfile,
    get_profile,
    load_custom_profiles,
    resolve_style,
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
    assert profile.end_of_response_sequence == b""
    assert profile.formfeed_on_close is True
    assert profile.instant_output is False
    assert profile.usb_vendor_id is None
    assert profile.usb_product_id is None
    assert profile.columns == 80
    assert profile.human_needed == ()


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


def test_builtin_profiles_count():
    """BUILTIN_PROFILES entry count: literals + aliases + catalog profiles."""
    assert len(BUILTIN_PROFILES) == 11


def test_builtin_profiles_keys():
    """BUILTIN_PROFILES has the expected profile names."""
    expected = {
        "generic", "escp", "ppds", "pcl", "ibm",
        "juki-6100", "juki-2200", "juki",
        "oki-3390",
        "citizen-cts2000",
        "escp2",
    }
    assert set(BUILTIN_PROFILES.keys()) == expected


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


def test_escp2_codes_match_escp_field_for_field():
    """escp2 (S03 catalog) style/init codes are verified identical to escp.

    ESC/P2 is a superset of ESC/P for these commands (Epson ESC/P2
    command summary) — the bytes must match field-for-field.
    """
    escp2 = BUILTIN_PROFILES["escp2"]
    escp = BUILTIN_PROFILES["escp"]
    for field_name in (
        "init_sequence", "reset_sequence", "line_spacing", "char_pitch",
        "bold_on", "bold_off",
        "italic_on", "italic_off",
        "underline_on", "underline_off",
        "crlf", "formfeed_on_close", "columns",
    ):
        assert getattr(escp2, field_name) == getattr(escp, field_name), (
            f"escp2.{field_name} diverges from escp"
        )


def test_escp2_codepage_pc437():
    """escp2 selects PC437 via ESC t 1 (ESC/P Reference Manual p. C-76)."""
    p = BUILTIN_PROFILES["escp2"]
    assert p.codepage_command == b"\x1bt\x01"  # ESC t 1 — table 1 = PC437
    assert p.text_codec == "cp437"


def test_escp2_no_usb_ids():
    """escp2 carries NO VID/PID: 0x04B8 is VID-only-claimed by escp (D007).

    LX-350/LQ-350 route to escp2 via detection.KNOWN_MODEL_PIDS, not the
    registry index — a VID claim here would collide with escp's.
    """
    p = BUILTIN_PROFILES["escp2"]
    assert p.usb_vendor_id is None
    assert p.usb_product_id is None


def test_escp2_no_human_needed_entries():
    """Every escp2 capability was verified from the manual — no gaps."""
    assert BUILTIN_PROFILES["escp2"].human_needed == ()


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


def test_citizen_profile_has_cp866_codepage():
    """citizen-cts2000 ships with CP866 codepage_command and cp866 text_codec."""
    p = get_profile("citizen-cts2000")
    assert p.codepage_command == b"\x1bt\x11"  # ESC t 17 — CP866
    assert p.text_codec == "cp866"


def test_load_custom_profiles_codepage_and_text_codec():
    """Custom TOML profiles can declare codepage_command (hex) and text_codec."""
    raw = {
        "printer": {
            "profiles": {
                "russian": {
                    "codepage_command": "1b7411",  # ESC t 17
                    "text_codec": "cp866",
                }
            }
        }
    }
    result = load_custom_profiles(raw)
    p = result["russian"]
    assert p.codepage_command == b"\x1bt\x11"
    assert p.text_codec == "cp866"


def test_load_custom_profiles_codepage_defaults_empty():
    """Profiles without codepage keys default to empty bytes / empty string."""
    raw = {
        "printer": {"profiles": {"plain": {"description": "ASCII only"}}}
    }
    result = load_custom_profiles(raw)
    p = result["plain"]
    assert p.codepage_command == b""
    assert p.text_codec == ""


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


def test_load_custom_profiles_buffer_bytes_rejects_zero():
    """buffer_bytes = 0 is rejected — Phase 26 chunker would loop forever."""
    raw = {
        "printer": {
            "profiles": {
                "bad": {"buffer_bytes": 0}
            }
        }
    }
    with pytest.raises(ValueError, match=r"buffer_bytes must be a positive integer"):
        load_custom_profiles(raw)


def test_load_custom_profiles_buffer_bytes_rejects_negative():
    """buffer_bytes = -64 is rejected — only positive integers are valid."""
    raw = {
        "printer": {
            "profiles": {
                "bad": {"buffer_bytes": -64}
            }
        }
    }
    with pytest.raises(ValueError, match=r"buffer_bytes must be a positive integer"):
        load_custom_profiles(raw)


def test_load_custom_profiles_buffer_bytes_rejects_non_int():
    """buffer_bytes = "256" (string) is rejected — would crash chunker arithmetic."""
    raw = {
        "printer": {
            "profiles": {
                "bad": {"buffer_bytes": "256"}
            }
        }
    }
    with pytest.raises(ValueError, match=r"buffer_bytes must be a positive integer"):
        load_custom_profiles(raw)


def test_load_custom_profiles_buffer_bytes_rejects_bool():
    """buffer_bytes = True is rejected — bool is an int subclass but not a real byte count."""
    raw = {
        "printer": {
            "profiles": {
                "bad": {"buffer_bytes": True}
            }
        }
    }
    with pytest.raises(ValueError, match=r"buffer_bytes must be a positive integer"):
        load_custom_profiles(raw)


def test_load_custom_profiles_human_needed_list_becomes_tuple():
    """A TOML human_needed list loads as a tuple (frozen dataclass field)."""
    raw = {
        "printer": {
            "profiles": {
                "partial": {
                    "human_needed": [
                        "italic codes unverified — needs the paper manual",
                        "codepage table number unverified",
                    ],
                }
            }
        }
    }
    result = load_custom_profiles(raw)
    p = result["partial"]
    assert p.human_needed == (
        "italic codes unverified — needs the paper manual",
        "codepage table number unverified",
    )
    assert isinstance(p.human_needed, tuple)


def test_load_custom_profiles_human_needed_absent_yields_empty_tuple():
    """Profiles without a human_needed key default to an empty tuple."""
    raw = {
        "printer": {"profiles": {"plain": {"description": "all verified"}}}
    }
    result = load_custom_profiles(raw)
    assert result["plain"].human_needed == ()


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
# Built-in profile style codes (Phase 22, CAP-04 + CAP-05)
# ---------------------------------------------------------------------------


class TestStyleCodesPerProfile:
    """Walk the Phase 22 encoding table cell-by-cell.

    Positive assertions confirm the exact bytes encoded for each verified
    capability. Negative assertions confirm intentionally-unsupported
    capabilities ARE empty bytes (not "missing" tests — they document the
    CAP-05 deferral pattern: Juki/OKI/Citizen italic, Juki bold).
    """

    # --- Epson ESC/P (escp) — CAP-04 ---

    def test_escp_bold_codes(self):
        p = BUILTIN_PROFILES["escp"]
        assert p.bold_on == b"\x1bE"
        assert p.bold_off == b"\x1bF"

    def test_escp_italic_codes(self):
        p = BUILTIN_PROFILES["escp"]
        assert p.italic_on == b"\x1b4"
        assert p.italic_off == b"\x1b5"

    def test_escp_underline_codes(self):
        p = BUILTIN_PROFILES["escp"]
        assert p.underline_on == b"\x1b-\x01"
        assert p.underline_off == b"\x1b-\x00"

    # --- IBM PPDS (ppds, alias ibm) — CAP-04 ---

    def test_ppds_bold_codes(self):
        p = BUILTIN_PROFILES["ppds"]
        assert p.bold_on == b"\x1bE"
        assert p.bold_off == b"\x1bF"

    def test_ppds_italic_codes(self):
        p = BUILTIN_PROFILES["ppds"]
        assert p.italic_on == b"\x1b%G"
        assert p.italic_off == b"\x1b%H"

    def test_ppds_underline_codes(self):
        p = BUILTIN_PROFILES["ppds"]
        assert p.underline_on == b"\x1b-\x01"
        assert p.underline_off == b"\x1b-\x00"

    def test_ibm_alias_inherits_ppds_style_codes(self):
        """The ibm alias picks up newly-encoded ppds codes via dataclasses.replace."""
        ibm = BUILTIN_PROFILES["ibm"]
        ppds = BUILTIN_PROFILES["ppds"]
        assert ibm.bold_on == ppds.bold_on == b"\x1bE"
        assert ibm.italic_on == ppds.italic_on == b"\x1b%G"
        assert ibm.underline_on == ppds.underline_on == b"\x1b-\x01"

    # --- HP PCL (pcl) — CAP-04 ---

    def test_pcl_bold_codes(self):
        p = BUILTIN_PROFILES["pcl"]
        assert p.bold_on == b"\x1b(s3B"
        assert p.bold_off == b"\x1b(s0B"

    def test_pcl_italic_codes(self):
        p = BUILTIN_PROFILES["pcl"]
        assert p.italic_on == b"\x1b(s1S"
        assert p.italic_off == b"\x1b(s0S"

    def test_pcl_underline_codes(self):
        p = BUILTIN_PROFILES["pcl"]
        assert p.underline_on == b"\x1b&dD"
        assert p.underline_off == b"\x1b&d@"

    # --- Juki 6100 (juki-6100, alias juki) — CAP-05 ---

    def test_juki_6100_underline_only(self):
        """Juki daisywheel: underline supported, bold/italic NOT SUPPORTED (deferred per CAP-05)."""
        p = BUILTIN_PROFILES["juki-6100"]
        assert p.underline_on == b"\x1b-\x01"
        assert p.underline_off == b"\x1b-\x00"

    def test_juki_6100_bold_intentionally_empty(self):
        """Bold via overstrike is not a one-shot ESC sequence — pipeline limitation, deferred."""
        p = BUILTIN_PROFILES["juki-6100"]
        assert p.bold_on == b""
        assert p.bold_off == b""

    def test_juki_6100_italic_intentionally_empty(self):
        """No italic daisywheel installed — hardware limitation."""
        p = BUILTIN_PROFILES["juki-6100"]
        assert p.italic_on == b""
        assert p.italic_off == b""

    def test_juki_alias_inherits_6100_underline_codes(self):
        """The juki alias picks up newly-encoded juki-6100 underline via dataclasses.replace."""
        juki = BUILTIN_PROFILES["juki"]
        six = BUILTIN_PROFILES["juki-6100"]
        assert juki.underline_on == six.underline_on == b"\x1b-\x01"
        assert juki.underline_off == six.underline_off == b"\x1b-\x00"
        assert juki.bold_on == b""
        assert juki.italic_on == b""

    # --- Juki 2200 (juki-2200) — CAP-05 ---

    def test_juki_2200_underline_only(self):
        p = BUILTIN_PROFILES["juki-2200"]
        assert p.underline_on == b"\x1b-\x01"
        assert p.underline_off == b"\x1b-\x00"

    def test_juki_2200_bold_intentionally_empty(self):
        p = BUILTIN_PROFILES["juki-2200"]
        assert p.bold_on == b""
        assert p.bold_off == b""

    def test_juki_2200_italic_intentionally_empty(self):
        p = BUILTIN_PROFILES["juki-2200"]
        assert p.italic_on == b""
        assert p.italic_off == b""

    # --- OKI Microline 3390 (oki-3390) — CAP-05 ---

    def test_oki_3390_bold_codes(self):
        p = BUILTIN_PROFILES["oki-3390"]
        assert p.bold_on == b"\x1bE"
        assert p.bold_off == b"\x1bF"

    def test_oki_3390_underline_codes(self):
        p = BUILTIN_PROFILES["oki-3390"]
        assert p.underline_on == b"\x1b-\x01"
        assert p.underline_off == b"\x1b-\x00"

    def test_oki_3390_italic_intentionally_empty(self):
        """OKI italic uses ESC! mode-bit composite — vendor-specific, deferred per CAP-05."""
        p = BUILTIN_PROFILES["oki-3390"]
        assert p.italic_on == b""
        assert p.italic_off == b""

    # --- Citizen CT-S2000 (citizen-cts2000) — CAP-05 ---

    def test_citizen_cts2000_bold_codes(self):
        """Citizen ESC/POS bold = ESC E n where n is BINARY 1/0 (NOT ASCII '1'/'0')."""
        p = BUILTIN_PROFILES["citizen-cts2000"]
        assert p.bold_on == b"\x1bE\x01"
        assert p.bold_off == b"\x1bE\x00"

    def test_citizen_cts2000_underline_codes(self):
        p = BUILTIN_PROFILES["citizen-cts2000"]
        assert p.underline_on == b"\x1b-\x01"
        assert p.underline_off == b"\x1b-\x00"

    def test_citizen_cts2000_italic_intentionally_empty(self):
        """Italic NOT SUPPORTED on thermal receipt printers."""
        p = BUILTIN_PROFILES["citizen-cts2000"]
        assert p.italic_on == b""
        assert p.italic_off == b""

    # --- Generic (no-op baseline) — CAP-05 ---

    def test_generic_all_style_fields_empty(self):
        """Generic profile is the no-op baseline — every style field is empty."""
        p = BUILTIN_PROFILES["generic"]
        assert p.bold_on == b""
        assert p.bold_off == b""
        assert p.italic_on == b""
        assert p.italic_off == b""
        assert p.underline_on == b""
        assert p.underline_off == b""


def test_builtin_profiles_paired_style_symmetry():
    """Every non-empty *_on byte field MUST have a non-empty *_off companion.

    A profile shipping `bold_on` without `bold_off` would leak the bold mode
    after a span ended — the renderer writes the on-bytes but has nothing to
    close the span with, so subsequent text prints in bold until the next
    init. Phase 21 REVIEW IN-05 flagged this; Phase 22 encodes codes on
    built-ins; this test prevents future encoding edits from introducing
    orphaned style-on codes.

    Both directions are checked: non-empty on -> non-empty off (mode-leakage
    prevention) AND non-empty off -> non-empty on (no orphan close codes
    that fire without a corresponding open).
    """
    style_pairs = (
        ("bold_on", "bold_off"),
        ("italic_on", "italic_off"),
        ("underline_on", "underline_off"),
    )
    for name, p in BUILTIN_PROFILES.items():
        for on_field, off_field in style_pairs:
            on_bytes = getattr(p, on_field)
            off_bytes = getattr(p, off_field)
            if on_bytes:
                assert off_bytes, (
                    f"{name}.{on_field} is non-empty but {off_field} is empty "
                    f"— this would leak the {on_field.replace('_on', '')} mode "
                    f"after spans close. See Phase 21 REVIEW IN-05."
                )
            if off_bytes:
                assert on_bytes, (
                    f"{name}.{off_field} is non-empty but {on_field} is empty "
                    f"— off-codes without on-codes would fire without ever "
                    f"opening the corresponding mode."
                )


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
