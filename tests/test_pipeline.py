"""Tests for printing/pipeline.py::render_document — the ONE shared pipeline.

Phase 33 (ARCH-01): the ~90-line print pipeline previously duplicated
between cli.py:_render_markdown_to_driver and tui.py:_run_print_pipeline
is consolidated into printing/pipeline.py::render_document. These tests
lock the shared core's contract:

- both speed modes (typewriter pacing via injectable sleep_fn; instant
  chunked style writes at profile.buffer_bytes)
- cancel-safety: PrintCancelled + `finally: renderer.close()` so style-off
  bytes reach the printer on every exit path (T-33-02)
- transcript fan-out taps ONLY the text channel (TXN-02 / T-33-03)
- driver ownership stays with adapters (render_document never closes)

Patch-target convention: render_document imports its deps LOCALLY, so
patches target SOURCE modules (claude_teletype.printing.drivers,
claude_teletype.transcript, ...) — same convention as tests/test_cli_print.py.
"""

import dataclasses

import pytest

from claude_teletype.printing.pipeline import PrintCancelled, render_document
from claude_teletype.printing.profiles import get_profile
from claude_teletype.rendering.pacer import CHAR_DELAYS, classify_char


class FakeDriver:
    """Recording driver: text channel via write, style channel via write_bytes.

    Deliberately has NO close() method — render_document must never call
    driver.close() (ownership stays with the adapters), so an accidental
    close raises AttributeError and fails the test loudly.
    """

    def __init__(self):
        self.events: list[tuple] = []
        self.end_response_calls = 0

    def write(self, char: str) -> None:
        self.events.append(("write", char))

    def write_bytes(self, data: bytes) -> None:
        self.events.append(("write_bytes", data))

    def end_response(self) -> None:
        self.end_response_calls += 1
        self.events.append(("end_response",))

    # -- helpers -------------------------------------------------------

    def text(self) -> str:
        return "".join(c for kind, c in
                       [e for e in self.events if e[0] == "write"])

    def style_payloads(self) -> list[bytes]:
        return [e[1] for e in self.events if e[0] == "write_bytes"]


def _escp(**overrides):
    """A real escp profile, optionally tweaked (buffer_bytes, bold_on, ...)."""
    profile = get_profile("escp")
    return dataclasses.replace(profile, **overrides) if overrides else profile


# ---------------------------------------------------------------------------
# Instant mode: chunked style writes
# ---------------------------------------------------------------------------


class TestInstantMode:
    def test_style_chunked_at_profile_buffer_bytes(self):
        """64-byte profile: a 100-byte style payload arrives as 64 + 36."""
        driver = FakeDriver()
        profile = _escp(buffer_bytes=64, bold_on=b"A" * 100)

        render_document(driver, profile, "**hi**\n", speed_mode="instant")

        payloads = driver.style_payloads()
        assert b"A" * 64 in payloads
        assert b"A" * 36 in payloads
        # 64-chunk precedes its 36-byte remainder
        assert payloads.index(b"A" * 64) < payloads.index(b"A" * 36)
        # Text chars arrive via the text channel
        assert "h" in driver.text() and "i" in driver.text()

    def test_falsy_buffer_bytes_falls_back_to_256(self):
        """buffer_bytes=0 (falsy) uses the 256 default (TUI getattr guard)."""
        driver = FakeDriver()
        profile = _escp(buffer_bytes=0, bold_on=b"B" * 300)

        render_document(driver, profile, "**x**\n", speed_mode="instant")

        payloads = driver.style_payloads()
        assert b"B" * 256 in payloads
        assert b"B" * 44 in payloads

    def test_profile_none_uses_columns_80_and_no_style_bytes(self):
        """profile=None: no style bytes; text wraps at the 80-column default."""
        driver = FakeDriver()
        long_text = " ".join(["word"] * 40) + "\n"  # 199 chars, must wrap

        render_document(driver, None, long_text, speed_mode="instant")

        assert driver.style_payloads() == []
        lines = driver.text().split("\n")
        assert any(lines), "text must have reached the driver"
        assert all(len(line) <= 80 for line in lines), (
            f"columns default must be 80; got line lengths "
            f"{[len(line) for line in lines]}"
        )
        assert len(lines) >= 3, "199 chars at 80 cols must wrap"


# ---------------------------------------------------------------------------
# Typewriter mode: injectable pacing
# ---------------------------------------------------------------------------


class TestTypewriterMode:
    def test_sleep_fn_paced_per_char_with_char_delays(self):
        """Each written char pays base_delay * CHAR_DELAYS[classify_char]."""
        driver = FakeDriver()
        sleeps: list[float] = []

        render_document(
            driver, None, "hi\n",
            speed_mode="typewriter",
            base_delay_ms=100.0,
            sleep_fn=sleeps.append,
        )

        chars = [e[1] for e in driver.events if e[0] == "write"]
        assert len(sleeps) == len(chars), (
            "exactly one sleep per written char"
        )
        for char, slept in zip(chars, sleeps):
            expected = 0.1 * CHAR_DELAYS[classify_char(char)]
            assert slept == pytest.approx(expected)

    def test_zero_delay_never_sleeps(self):
        driver = FakeDriver()
        sleeps: list[float] = []

        render_document(
            driver, None, "hi\n",
            speed_mode="typewriter",
            base_delay_ms=0.0,
            sleep_fn=sleeps.append,
        )

        assert sleeps == []
        assert "h" in driver.text()

    def test_style_bytes_not_chunked(self):
        """Typewriter mode sends style bursts straight to write_bytes."""
        driver = FakeDriver()
        profile = _escp(buffer_bytes=64, bold_on=b"A" * 100)

        render_document(
            driver, profile, "**hi**\n",
            speed_mode="typewriter",
            base_delay_ms=0.0,
            sleep_fn=lambda s: None,
        )

        assert b"A" * 100 in driver.style_payloads(), (
            "100-byte burst must arrive whole (no chunking in typewriter mode)"
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSpeedModeValidation:
    def test_invalid_speed_mode_raises_before_any_driver_call(self):
        driver = FakeDriver()
        with pytest.raises(ValueError):
            render_document(driver, None, "hi\n", speed_mode="garbage")
        assert driver.events == []


# ---------------------------------------------------------------------------
# Cancel-safety (T-33-02): PrintCancelled + finally: renderer.close()
# ---------------------------------------------------------------------------


class TestCancelSafety:
    def test_cancel_mid_bold_raises_and_emits_style_off(self):
        """Cancel inside an open **bold** span: PrintCancelled propagates AND
        renderer.close() ran (bold_off ESC F reached the style channel)."""
        driver = FakeDriver()
        calls = {"n": 0}

        def cancel_after_two():
            calls["n"] += 1
            return calls["n"] > 2

        with pytest.raises(PrintCancelled):
            render_document(
                driver, _escp(), "**bold text**\n",
                speed_mode="instant",
                cancel_check=cancel_after_two,
            )

        # escp bold_off is ESC F — must appear (renderer.close() in finally)
        assert b"\x1bF" in driver.style_payloads(), (
            "renderer.close() must emit bold_off on cancel"
        )
        assert driver.end_response_calls == 0, (
            "end_response must NOT run on cancel"
        )

    def test_driver_error_still_closes_renderer_and_propagates(self):
        """Driver exploding mid-render: renderer.close() still runs, and the
        exception is NOT swallowed."""

        class ExplodingDriver(FakeDriver):
            def write(self, char: str) -> None:
                super().write(char)
                raise RuntimeError("boom")

        driver = ExplodingDriver()
        with pytest.raises(RuntimeError, match="boom"):
            render_document(driver, _escp(), "**bold**\n",
                            speed_mode="instant")

        assert b"\x1bF" in driver.style_payloads(), (
            "renderer.close() must emit bold_off on driver error"
        )
        assert driver.end_response_calls == 0


# ---------------------------------------------------------------------------
# Transcript fan-out (TXN-02 / T-33-03)
# ---------------------------------------------------------------------------


class TestTranscriptFanOut:
    def test_transcript_captures_plain_text_only(self, tmp_path):
        driver = FakeDriver()
        captured: list[str] = []
        src = tmp_path / "doc.md"
        src.write_text("**bold**\n")

        render_document(
            driver, _escp(), "**bold**\n",
            speed_mode="instant",
            transcript_write=captured.append,
            source_path=src,
        )

        joined = "".join(captured)
        assert "bold" in joined
        assert "\x1b" not in joined, "TXN-02: no ESC bytes in transcript"
        assert "Printed file:" in joined

    def test_write_printed_file_called_once(self, tmp_path):
        from unittest.mock import patch

        import claude_teletype.transcript as transcript_mod

        driver = FakeDriver()
        captured: list[str] = []
        src = tmp_path / "doc.md"
        src.write_text("hello\n")

        with patch(
            "claude_teletype.transcript.write_printed_file",
            wraps=transcript_mod.write_printed_file,
        ) as wpf:
            render_document(
                driver, None, "hello\n",
                transcript_write=captured.append,
                source_path=src,
            )
        assert wpf.call_count == 1
        # Body arg is the joined plain-text collector output
        body = wpf.call_args.args[2]
        assert "hello" in body
        assert "\x1b" not in body

    def test_no_transcript_write_no_call(self):
        from unittest.mock import patch

        driver = FakeDriver()
        with patch(
            "claude_teletype.transcript.write_printed_file",
        ) as wpf:
            render_document(driver, None, "hello\n", transcript_write=None)
        wpf.assert_not_called()


# ---------------------------------------------------------------------------
# Epilogue + driver ownership
# ---------------------------------------------------------------------------


class TestEpilogue:
    def test_end_response_called_once_on_success(self):
        driver = FakeDriver()
        render_document(driver, _escp(), "hi\n")
        assert driver.end_response_calls == 1

    def test_end_response_skipped_when_driver_lacks_it(self):
        class BareDriver:
            def __init__(self):
                self.chars: list[str] = []

            def write(self, char):
                self.chars.append(char)

            def write_bytes(self, data):
                pass

        driver = BareDriver()
        render_document(driver, None, "hi\n")  # must not crash
        assert "hi" in "".join(driver.chars)

    def test_render_document_never_closes_driver(self):
        from unittest.mock import MagicMock

        driver = MagicMock(spec=["write", "write_bytes", "close"])
        render_document(driver, None, "hi\n")
        driver.close.assert_not_called()
