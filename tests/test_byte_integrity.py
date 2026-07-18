"""Byte-integrity regression tests (BYTE-03 contract lock).

Locks the driver-layer guarantee that bytes >= 0x80 survive the trip
from ProfilePrinterDriver / CupsPrinterDriver to the wire verbatim.

Sentinel: the ppds profile's codepage_command ends in 0xb5 (CP 437 =
1*256 + 181). Any ASCII round-trip in the driver layer mangles it to
0x3f ('?'), silently selecting code page 319 instead of 437 (CR-01)
and printing cp437/cp866 text as '?' over CUPS (CR-02).

Driver-layer contract lock only — no imports from teletype.py.
"""

from unittest.mock import MagicMock, patch

from claude_teletype.printing.drivers import CupsPrinterDriver, ProfilePrinterDriver
from claude_teletype.printing.profiles import PrinterProfile, get_profile

# ppds codepage select: ESC [ T 4 0 0 0 1 181 — trailing byte 0xb5
PPDS_CODEPAGE_CMD = b"\x1b[T\x04\x00\x00\x00\x01\xb5"


def _bytes_reaching_inner(inner: MagicMock) -> bytes:
    """Reconstruct the byte stream the inner driver saw, in call order.

    write() carries str (ASCII-encoded on the wire); write_bytes()
    carries raw bytes. Interleaving is preserved via mock_calls.
    """
    out = b""
    for name, args, _kwargs in inner.mock_calls:
        if name == "write":
            out += args[0].encode("ascii", errors="replace")
        elif name == "write_bytes":
            out += args[0]
    return out


def test_profile_write_bytes_delivers_high_bytes_verbatim():
    """BYTE-01: raw write_bytes path delivers 0xb5 via inner.write_bytes."""
    inner = MagicMock()
    inner.is_connected = True
    ppd = ProfilePrinterDriver(inner, PrinterProfile(name="test"))

    ppd.write_bytes(PPDS_CODEPAGE_CMD)

    inner.write_bytes.assert_called_once_with(PPDS_CODEPAGE_CMD)
    inner.write.assert_not_called()  # str channel must not carry raw bytes


def test_profile_codepage_text_path_preserves_high_bytes():
    """BYTE-01: ppds codepage command AND cp437-encoded text reach inner intact."""
    inner = MagicMock()
    inner.is_connected = True
    ppd = ProfilePrinterDriver(inner, get_profile("ppds"))

    ppd.write("─")  # BOX DRAWINGS LIGHT HORIZONTAL -> cp437 0xc4

    raw = _bytes_reaching_inner(inner)
    assert PPDS_CODEPAGE_CMD in raw  # trailing 0xb5 intact, not 0x3f
    assert b"\xc4" in raw  # encoded text byte intact
    assert b"\x3f" not in raw  # no '?' substitution anywhere


@patch("claude_teletype.printing.drivers.subprocess.run")
def test_cups_write_bytes_preserves_high_bytes(mock_run: MagicMock):
    """BYTE-02: CupsPrinterDriver hands 0xb5 to lp stdin verbatim."""
    driver = CupsPrinterDriver("q")

    driver.write_bytes(PPDS_CODEPAGE_CMD)
    driver.write("\n")

    mock_run.assert_called_once()
    sent = mock_run.call_args.kwargs["input"]
    assert sent == PPDS_CODEPAGE_CMD + b"\n"
    assert b"\xb5" in sent
    assert b"\x3f" not in sent


@patch("claude_teletype.printing.drivers.subprocess.run")
def test_composed_ppds_over_cups_round_trip(mock_run: MagicMock):
    """BYTE-01+02: ppds over CUPS — codepage command and text bytes unaltered."""
    mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
    ppd = ProfilePrinterDriver(CupsPrinterDriver("q"), get_profile("ppds"))

    ppd.write("─")
    ppd.write("\n")

    sent = b"".join(
        c.kwargs.get("input", b"") for c in mock_run.call_args_list
    )
    assert PPDS_CODEPAGE_CMD in sent
    assert b"\xc4" in sent
    assert b"\x3f" not in sent
