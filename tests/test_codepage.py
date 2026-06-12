"""DIR-01 codepage formalization: custom-TOML load + driver consumption.

Covers the three codepage fields on PrinterProfile:

  codepage_command — lazy one-shot codepage select sequence
  text_codec       — codec used to encode non-ASCII chunks as raw bytes
  text_fallback    — per-char transliteration applied BEFORE codec encoding

Load coverage parses a real TOML fixture (tests/fixtures/
custom_codepage_profile.toml) through load_custom_profiles and asserts
each field's decoding convention. Consumption coverage drives the real
ProfilePrinterDriver against a capturing sink and locks in:

  1. text_fallback substitution happens before codec encoding
  2. codepage_command is emitted lazily, exactly once per session
  3. the CR+LF+reinit newline transfer is a SINGLE atomic write
     (locked invariant — fragmented transfers drop bytes on CH341)
"""

import tomllib
from pathlib import Path

import pytest

from claude_teletype.printing.drivers import ProfilePrinterDriver
from claude_teletype.printing.profiles import (
    PrinterProfile,
    load_custom_profiles,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "custom_codepage_profile.toml"


def _load_fixture_profile() -> PrinterProfile:
    """Parse the custom-TOML fixture through the real load path."""
    with open(FIXTURE_PATH, "rb") as f:
        raw = tomllib.load(f)
    profiles = load_custom_profiles(raw)
    return profiles["cyrillic-custom"]


class CapturingDriver:
    """Inner-driver test double that records every call in order.

    Each entry is ("write", str) or ("write_bytes", bytes) — one entry
    per call, so call-boundary (atomicity) assertions are possible.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.is_connected = True

    def write(self, char: str) -> None:
        self.calls.append(("write", char))

    def write_bytes(self, data: bytes) -> None:
        self.calls.append(("write_bytes", data))

    def close(self) -> None:
        pass

    def raw(self) -> bytes:
        """All output flattened to bytes (write strs ASCII-encoded)."""
        out = b""
        for kind, payload in self.calls:
            if kind == "write":
                out += payload.encode("ascii", errors="replace")
            else:
                out += payload
        return out


# ---------------------------------------------------------------------------
# Task 1: custom-TOML fixture load coverage
# ---------------------------------------------------------------------------


def test_fixture_codepage_command_parses_hex_to_bytes():
    """codepage_command hex string in TOML decodes via bytes.fromhex."""
    profile = _load_fixture_profile()
    assert profile.codepage_command == bytes.fromhex("1b7411")
    assert profile.codepage_command == b"\x1bt\x11"  # ESC t 17


def test_fixture_text_codec_stored_verbatim():
    """text_codec is stored as the exact literal string from TOML."""
    profile = _load_fixture_profile()
    assert profile.text_codec == "cp866"


def test_fixture_text_fallback_parses_table_to_dict():
    """text_fallback TOML table loads as the expected str->str dict."""
    profile = _load_fixture_profile()
    assert profile.text_fallback == {
        "і": "i",
        "І": "I",
        "—": "--",
        "…": "...",
    }


def test_fixture_non_codepage_fields_load_alongside():
    """Codepage fields coexist with ordinary profile fields in the TOML."""
    profile = _load_fixture_profile()
    assert profile.name == "cyrillic-custom"
    assert profile.crlf is True
    assert profile.formfeed_on_close is False


def test_codepage_fields_default_empty_without_toml_keys():
    """Profiles that don't opt in get empty codepage defaults."""
    raw = {"printer": {"profiles": {"plain": {}}}}
    profile = load_custom_profiles(raw)["plain"]
    assert profile.codepage_command == b""
    assert profile.text_codec == ""
    assert profile.text_fallback == {}


def test_codepage_command_rejects_invalid_hex():
    """Malformed codepage_command hex raises ValueError (bytes.fromhex)."""
    raw = {
        "printer": {
            "profiles": {"bad": {"codepage_command": "not-hex!"}}
        }
    }
    with pytest.raises(ValueError):
        load_custom_profiles(raw)


# ---------------------------------------------------------------------------
# Task 2: ProfilePrinterDriver consumption coverage
# ---------------------------------------------------------------------------


def _codepage_profile(**overrides) -> PrinterProfile:
    """A minimal in-test profile with all three codepage fields set."""
    kwargs = dict(
        name="codepage-test",
        codepage_command=b"\x1bt\x11",
        text_codec="cp866",
        text_fallback={"і": "i", "—": "--"},
    )
    kwargs.update(overrides)
    return PrinterProfile(**kwargs)


def test_text_fallback_applied_before_codec():
    """A mapped char is substituted BEFORE encoding — the fallback result
    (pure ASCII here) flows through the plain write path, so no codepage
    command and no codec bytes are emitted."""
    sink = CapturingDriver()
    driver = ProfilePrinterDriver(sink, _codepage_profile())

    driver.write("і")  # Ukrainian і — mapped to ASCII "i" by text_fallback

    assert ("write", "i") in sink.calls
    assert b"\x1bt\x11" not in sink.raw()
    # Nothing went through the raw-bytes codec path
    assert all(kind == "write" for kind, _ in sink.calls)


def test_multichar_fallback_substitution():
    """Multi-char replacement values are expanded in place (em-dash -> --)."""
    sink = CapturingDriver()
    driver = ProfilePrinterDriver(sink, _codepage_profile())

    driver.write("a—b")

    assert ("write", "a--b") in sink.calls


def test_codepage_command_lazy_not_sent_for_ascii():
    """Plain-ASCII writes never trigger the codepage command."""
    sink = CapturingDriver()
    driver = ProfilePrinterDriver(sink, _codepage_profile())

    driver.write("hello")
    driver.write("world")

    assert b"\x1bt\x11" not in sink.raw()


def test_codepage_command_emitted_once_then_codec_bytes():
    """First non-ASCII write emits codepage_command, then the chunk is
    encoded with text_codec and shipped via write_bytes."""
    sink = CapturingDriver()
    driver = ProfilePrinterDriver(sink, _codepage_profile())

    driver.write("Ж")  # Cyrillic Zhe — in CP866, no fallback mapping

    raw = sink.raw()
    assert raw.count(b"\x1bt\x11") == 1
    assert ("write_bytes", "Ж".encode("cp866")) in sink.calls
    # Command precedes the encoded payload
    assert raw.find(b"\x1bt\x11") < raw.find("Ж".encode("cp866"))


def test_codepage_command_not_repeated_across_writes():
    """codepage_command appears exactly once across many non-ASCII writes."""
    sink = CapturingDriver()
    driver = ProfilePrinterDriver(sink, _codepage_profile())

    driver.write("hello")  # ASCII — no command
    driver.write("Жук")    # first non-ASCII — command fires
    driver.write("привет")  # already sent — no repeat
    driver.write("мир")

    assert sink.raw().count(b"\x1bt\x11") == 1


def test_no_codepage_command_still_encodes_via_codec():
    """text_codec without codepage_command skips the select sequence but
    still encodes non-ASCII chunks as raw codec bytes."""
    sink = CapturingDriver()
    profile = _codepage_profile(codepage_command=b"")
    driver = ProfilePrinterDriver(sink, profile)

    driver.write("Ж")

    assert ("write_bytes", "Ж".encode("cp866")) in sink.calls
    assert b"\x1bt\x11" not in sink.raw()


def test_fixture_profile_drives_consumption_end_to_end():
    """The TOML-fixture-loaded profile drives the real driver: fallback,
    lazy-once codepage emission, and codec encoding all work from TOML."""
    sink = CapturingDriver()
    driver = ProfilePrinterDriver(sink, _load_fixture_profile())

    driver.write("і")    # fallback -> ASCII "i", no codepage yet
    driver.write("Жук")  # triggers ESC t 17 once, CP866 bytes follow
    driver.write("мир")  # no second codepage command

    raw = sink.raw()
    assert ("write", "i") in sink.calls
    assert raw.count(b"\x1bt\x11") == 1
    assert ("write_bytes", "Жук".encode("cp866")) in sink.calls


# ---------------------------------------------------------------------------
# Locked invariant: atomic CR+LF+reinit newline transfer
# ---------------------------------------------------------------------------


def test_newline_is_single_atomic_write_with_crlf_and_reinit():
    """write('\\n') ships CR+LF+reinit as ONE write call — the locked
    invariant. Fragmented transfers drop bytes on the CH341 bridge."""
    sink = CapturingDriver()
    profile = PrinterProfile(
        name="atomic-test",
        crlf=True,
        reinit_on_newline=True,
        reinit_sequence=b"\x1b\x1e\x09\x1bQ",
    )
    driver = ProfilePrinterDriver(sink, profile)
    driver._initialized = True  # skip init so only the newline is captured

    driver.write("\n")

    assert len(sink.calls) == 1
    kind, payload = sink.calls[0]
    assert kind == "write"
    assert payload == "\r\n\x1b\x1e\x09\x1bQ"


def test_newline_atomic_on_codepage_profile():
    """Newlines bypass text_fallback/codec and stay a single atomic
    transfer even on a profile with all codepage fields set."""
    sink = CapturingDriver()
    profile = _codepage_profile(crlf=True)
    driver = ProfilePrinterDriver(sink, profile)
    driver._initialized = True

    driver.write("Ж")   # codepage command + codec bytes
    before = len(sink.calls)
    driver.write("\n")

    newline_calls = sink.calls[before:]
    assert newline_calls == [("write", "\r\n")]
