"""Printer driver backends and resilient output wrappers.

Driver classes implementing the PrinterDriver Protocol, plus the
profile-aware output helpers (make_printer_output, chunk_writes).
Moved from the former top-level printer.py (drivers slice).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from claude_teletype.printing.profiles import PrinterProfile, get_profile


@runtime_checkable
class PrinterDriver(Protocol):
    """Interface for all printer backends."""

    @property
    def is_connected(self) -> bool: ...

    def write(self, char: str) -> None: ...

    def write_bytes(self, data: bytes) -> None: ...

    def close(self) -> None: ...


class NullPrinterDriver:
    """No-op driver for simulator-only mode."""

    @property
    def is_connected(self) -> bool:
        return False

    def write(self, char: str) -> None:
        pass

    def write_bytes(self, data: bytes) -> None:
        pass

    def close(self) -> None:
        pass


class FilePrinterDriver:
    """Direct device file I/O driver."""

    def __init__(self, device_path: str) -> None:
        self._path = device_path
        self._fd = open(device_path, "wb", buffering=0)
        self._connected = True

    @property
    def is_connected(self) -> bool:
        return self._connected

    def write(self, char: str) -> None:
        if not self._connected:
            return
        try:
            self._fd.write(char.encode("ascii", errors="replace"))
        except (OSError, ValueError):
            self._connected = False

    def write_bytes(self, data: bytes) -> None:
        if not self._connected:
            return
        if not data:
            return
        try:
            self._fd.write(data)
        except (OSError, ValueError):
            self._connected = False

    def close(self) -> None:
        if self._fd and not self._fd.closed:
            self._fd.close()


class CupsPrinterDriver:
    """CUPS raw queue driver using lp subprocess.

    Flushes each line as a separate lp job for real-time output.
    """

    def __init__(self, printer_name: str) -> None:
        self._name = printer_name
        self._connected = True
        self._line_buffer: list[str] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def write(self, char: str) -> None:
        if not self._connected:
            return
        self._line_buffer.append(char)
        if char == "\n":
            self._flush_line()

    def _flush_line(self) -> None:
        line = "".join(self._line_buffer)
        self._line_buffer.clear()
        try:
            subprocess.run(
                ["lp", "-o", "raw", "-d", self._name],
                input=line.encode("ascii", errors="replace"),
                capture_output=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            self._connected = False

    def flush(self) -> None:
        """Force-flush the line buffer even without a trailing newline.

        Needed for ESC sequences (paper cut, init/reset) that have no \\n
        terminator — without this they would sit in the buffer until the
        next text line arrived, and per-response cuts would never fire.
        """
        if self._line_buffer and self._connected:
            self._flush_line()

    def write_bytes(self, data: bytes) -> None:
        if not self._connected:
            return
        if not data:
            return
        text = data.decode("ascii", errors="replace")
        self._line_buffer.append(text)
        if "\n" in text:
            self._flush_line()

    def close(self) -> None:
        if self._line_buffer:
            self._flush_line()


class UsbPrinterDriver:
    """Direct USB bulk-transfer driver via pyusb, bypassing CUPS."""

    def __init__(self, dev: Any, ep_out: Any) -> None:
        self._dev = dev
        self._ep_out = ep_out
        self._connected = True

    @property
    def is_connected(self) -> bool:
        return self._connected

    def write(self, char: str) -> None:
        if not self._connected:
            return
        try:
            self._ep_out.write(char.encode("ascii", errors="replace"))
        except Exception:
            self._connected = False

    def write_bytes(self, data: bytes) -> None:
        if not self._connected:
            return
        if not data:
            return
        try:
            self._ep_out.write(data)
        except Exception:
            self._connected = False

    def close(self) -> None:
        if self._dev is not None:
            try:
                import usb.util

                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
            self._dev = None


class ProfilePrinterDriver:
    """Profile-driven printer wrapper.

    Wraps an inner PrinterDriver, prepending ESC initialization codes on first
    write and handling newline strategy (CR+LF vs LF-only) based on the
    profile's configuration.
    """

    def __init__(self, inner: PrinterDriver, profile: PrinterProfile) -> None:
        self._inner = inner
        self._profile = profile
        self._initialized = False
        # Tracks whether content has been written since the last
        # end_response() / close() so we don't cut blank paper if flush is
        # called twice (e.g. cancel + error paths both calling _flush_printer).
        self._has_unflushed_output = False
        # Tracks whether the profile's codepage_command has been emitted
        # for the current session. Lazy: only sent the first time a
        # non-ASCII char appears, so ASCII-only documents pay no penalty
        # and the printer stays in its default codepage.
        self._codepage_sent = False

    def _send_raw(self, data: bytes) -> None:
        """Send raw bytes through the inner driver as a single write.

        Sending ESC sequences atomically prevents the printer from
        misinterpreting fragmented escape codes (e.g., Juki 6100 drops
        characters when init/reinit bytes arrive as individual USB transfers).
        """
        if data:
            self._inner.write(data.decode("ascii", errors="replace"))

    def _ensure_init(self) -> None:
        if not self._initialized:
            self._initialized = True
            init_data = (
                self._profile.init_sequence
                + self._profile.line_spacing
                + self._profile.char_pitch
            )
            if init_data:
                self._send_raw(init_data)

    @property
    def is_connected(self) -> bool:
        return self._inner.is_connected

    def write(self, char: str) -> None:
        if not self._inner.is_connected:
            return
        self._ensure_init()
        self._has_unflushed_output = True
        # Apply per-char transliteration before any codec encoding. This
        # lets profiles substitute glyphs that are missing from their
        # code page (e.g. Ukrainian "і" → Latin "i" on CP866) instead of
        # the codec's "?" replacement. After substitution, the chunk may
        # be pure ASCII and skip the codepage path entirely.
        if self._profile.text_fallback and char != "\n":
            char = "".join(
                self._profile.text_fallback.get(c, c) for c in char
            )
        if char == "\n":
            # Send CR+LF+reinit as a single atomic transfer.
            # Fragmented USB transfers cause the Juki 6100 (CH341 bridge)
            # to drop bytes — especially the LF after CR, which results
            # in carriage return without paper advance on wrapped lines.
            newline_data = b""
            if self._profile.crlf:
                newline_data += b"\r"
            newline_data += b"\n"
            if self._profile.reinit_on_newline and self._profile.reinit_sequence:
                newline_data += self._profile.reinit_sequence
            self._send_raw(newline_data)
        elif self._needs_codepage(char):
            # Chunk contains at least one non-ASCII char on a profile with
            # a configured text_codec. Lazy-send the codepage command once,
            # then encode the whole chunk via the profile's codec and ship
            # it as raw bytes — bypassing the ASCII decode path in _send_raw
            # which would replace non-ASCII chars with '?'. ASCII chars in
            # the chunk survive intact because CP866 (and most ESC/POS code
            # pages) preserve 0x00-0x7F verbatim.
            self._ensure_codepage()
            encoded = char.encode(self._profile.text_codec, errors="replace")
            self._inner.write_bytes(encoded)
        else:
            self._inner.write(char)

    def _needs_codepage(self, char: str) -> bool:
        """True when the chunk contains any non-ASCII char on a codepage profile.

        ``char`` is named for the protocol but may be a multi-char string
        (WordWrapper batches whole words into one ``write`` call). Returns
        False for ASCII-only chunks and for profiles without a configured
        ``text_codec`` — those flow through the original write path.
        """
        if not self._profile.text_codec:
            return False
        return any(ord(c) > 0x7F for c in char)

    def _ensure_codepage(self) -> None:
        """Emit ``codepage_command`` exactly once per session.

        Called lazily on the first non-ASCII char. Profiles with no
        ``codepage_command`` (e.g. ``text_codec`` set without a select
        sequence) skip the send and just rely on the codec encoding,
        which works for printers whose default codepage already matches.
        """
        if self._codepage_sent:
            return
        self._codepage_sent = True
        if self._profile.codepage_command:
            self._send_raw(self._profile.codepage_command)

    def write_bytes(self, data: bytes) -> None:
        """Send raw bytes (e.g., ESC style sequences) as a single atomic transfer.

        Used by the markdown renderer's style channel for bold/italic/underline
        ESC sequences. Bypasses per-character newline handling — the caller is
        responsible for NOT passing newline byte sequences through this method.
        Use ``write("\\n")`` for newlines (preserves the atomic CR+LF + reinit
        pattern required by MD-08).
        """
        if not self._inner.is_connected:
            return
        if not data:
            return
        self._ensure_init()
        self._has_unflushed_output = True
        self._send_raw(data)

    def swap_profile(self, new_profile: PrinterProfile) -> None:
        """Replace the current profile and mark as uninitialized.

        The new profile's init sequences will be sent on the next write().
        Resets the codepage-sent flag so the new profile's
        ``codepage_command`` (if any) fires on the next non-ASCII char.
        """
        self._profile = new_profile
        self._initialized = False
        self._codepage_sent = False

    def end_response(self) -> None:
        """Emit the profile's end-of-response sequence (e.g. paper cut).

        No-op when the profile has no end_of_response_sequence, when the
        printer has not been initialized, when the inner driver is
        disconnected, or when no content has been written since the last
        end_response (avoids cutting blank paper on duplicate flush calls).
        """
        if not self._initialized or not self._inner.is_connected:
            return
        if not self._has_unflushed_output:
            return
        if self._profile.end_of_response_sequence:
            self._send_raw(self._profile.end_of_response_sequence)
            # Drivers that batch by line (CupsPrinterDriver) leave the
            # cut bytes stuck in the buffer because the sequence has no
            # \n. Force a flush so the bytes actually reach the printer.
            inner_flush = getattr(self._inner, "flush", None)
            if inner_flush is not None:
                inner_flush()
        self._has_unflushed_output = False

    def close(self) -> None:
        if self._initialized and self._inner.is_connected:
            # If the last response wasn't flushed cleanly (forceful exit
            # mid-stream), cut the partial output before resetting.
            self.end_response()
            if self._profile.formfeed_on_close:
                self._inner.write("\f")
            if self._profile.reset_sequence:
                self._send_raw(self._profile.reset_sequence)
        self._inner.close()


class JukiPrinterDriver(ProfilePrinterDriver):
    """Juki 6100 daisywheel impact printer driver.

    Deprecated: use ProfilePrinterDriver with get_profile("juki").
    Kept as backward-compatible alias.
    """

    # Juki 6100 ESC sequences (kept for backward compat in tests)
    RESET = b"\x1b\x1aI"  # ESC SUB I — full reset
    LINE_SPACING = b"\x1b\x1e\x09"  # ESC RS 9 — 1/6" line spacing
    FIXED_PITCH = b"\x1bQ"  # ESC Q — disable proportional spacing

    def __init__(self, inner: PrinterDriver) -> None:
        super().__init__(inner, get_profile("juki"))


A4_COLUMNS = 80  # A4 printable width at 10 CPI (pica)


def make_printer_output(
    driver: PrinterDriver, columns: int = A4_COLUMNS
) -> Callable[[str], None]:
    """Create an output_fn that writes to a printer with word-wrap and graceful degradation.

    Uses WordWrapper at the given column width for word-boundary wrapping.
    On IOError/OSError, stops writing permanently (PRNT-03).

    The returned callable has a ``.flush()`` attribute that emits any
    buffered word without adding a trailing newline.  Callers *must*
    invoke it at the end of every response to avoid leaving the last
    word stranded in the buffer.
    """
    from claude_teletype.wordwrap import WordWrapper

    disconnected = False

    def safe_write(char: str) -> None:
        nonlocal disconnected
        if disconnected:
            return
        try:
            driver.write(char)
        except OSError:
            disconnected = True

    wrapper = WordWrapper(columns, safe_write)

    def printer_write(char: str) -> None:
        if disconnected:
            return
        if char in ("\r", "\f"):
            wrapper.flush()
            safe_write(char)
            wrapper.reset_column()
        else:
            wrapper.feed(char)

    def printer_flush() -> None:
        nonlocal disconnected
        if disconnected:
            return
        wrapper.flush()
        # Per-response hook: lets profile-aware drivers emit a separator
        # (e.g. receipt printer paper cut) at end of each LLM response.
        end = getattr(driver, "end_response", None)
        if end is not None:
            try:
                end()
            except OSError:
                disconnected = True

    printer_write.flush = printer_flush  # type: ignore[attr-defined]

    return printer_write


def chunk_writes(
    driver: PrinterDriver,
    data: bytes,
    chunk_size: int,
) -> None:
    """Split a bytes payload into chunk_size-byte writes (Phase 26 FLOW-04).

    Used by Phase 26's instant-mode pipeline to prevent buffer overruns on
    impact printers. The Juki/CH341 USB-LPT bridge in particular drops
    bytes when bulk transfers exceed the bridge's 64-byte buffer; the
    profile.buffer_bytes field encodes the per-printer safe chunk size
    (juki=64, citizen=128, generic=256).

    Each chunk reaches the driver via driver.write_bytes — no per-character
    driver.write calls, so the MD-08 newline contract is preserved
    (newlines stay on the text channel and never enter chunk_writes).

    Args:
        driver: A PrinterDriver. write_bytes is called once per chunk.
        data: The raw bytes to split. Empty -> no-op (no driver call).
        chunk_size: Slice length. Must be positive.

    Raises:
        ValueError: If chunk_size <= 0.
    """
    if chunk_size <= 0:
        raise ValueError(
            f"chunk_size must be positive, got {chunk_size}"
        )
    if not data:
        return
    for i in range(0, len(data), chunk_size):
        driver.write_bytes(data[i : i + chunk_size])
