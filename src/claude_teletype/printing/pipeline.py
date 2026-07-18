"""The ONE shared print pipeline (Phase 33, ARCH-01).

``render_document`` is the single implementation of the render-to-printer
pipeline previously duplicated (~90 lines each) between
``cli.py:_render_markdown_to_driver`` and ``tui.py:_run_print_pipeline``.
A pipeline change is now a one-place edit.

Semantics decided ONCE (merging the two prior copies):

- speed_mode validation up front (from the CLI copy) — raises ``ValueError``
  before any driver call; adapters map it to their own error surface.
- ``finally: renderer.close()`` cancel-safety (from the TUI copy, FLOW-05):
  a mid-render exception or cancel emits the LIFO style-off bytes
  (italic_off before bold_off) so the printer never keeps leaked
  bold/italic state (T-33-02).
- getattr-guarded ``buffer_bytes`` fallback to 256 (the TUI's safest form).
- MD-08 stays intact by construction: newlines travel through
  ``driver.write('\\n')`` on the text channel; ``write_bytes`` remains the
  style channel; ``chunk_writes`` never sees newlines.

Driver ownership: render_document NEVER closes the driver. The CLI adapter
owns a fresh driver per invocation and closes it; the TUI's persistent
``self.printer`` must survive across prints. Closing here would break both.

Injectable seams for the two consumer shapes:

- ``sleep_fn``: pacing sleep (defaults to time.sleep(); the sync CLI path
  keeps the locked v1.5 pacing shape via this default, while the TUI's
  thread-worker consumer in Plan 33-02 injects a cancellable sleep).
- ``cancel_check``: polled between characters on the text channel; when it
  returns True, ``PrintCancelled`` is raised (WR-01 between-characters
  check — works identically in both speed modes).
"""

import time
from collections.abc import Callable
from pathlib import Path


class PrintCancelled(Exception):
    """Raised by ``render_document`` when ``cancel_check`` returns True.

    Adapters catch it: the render stopped cleanly (style-off bytes were
    emitted via ``finally: renderer.close()``), no transcript entry was
    written, and ``end_response`` did not run.
    """


def render_document(
    driver,
    profile,
    text: str,
    *,
    speed_mode: str = "instant",
    base_delay_ms: float = 0.0,
    no_audio: bool = True,
    transcript_write: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> None:
    """Render markdown ``text`` through ``driver`` — the one shared pipeline.

    Args:
        driver: PrinterDriver. ``write`` is the text channel (newlines MUST
            go here — MD-08); ``write_bytes`` is the style channel.
            NOT closed by this function — ownership stays with the caller.
        profile: PrinterProfile or None (None = generic: 80 columns,
            256-byte chunks, no style bytes emitted by the renderer).
        text: The document body (already read from disk by the adapter).
        speed_mode: "typewriter" (per-char pacing + bell) or "instant"
            (unpaced text, style writes chunked at profile.buffer_bytes).
        base_delay_ms: Typewriter base delay in milliseconds; 0 disables
            pacing entirely (sleep_fn is never called).
        no_audio: Suppress the bell in typewriter mode.
        transcript_write: Optional per-character transcript writer. When
            provided, the renderer's TEXT channel is fanned out into a
            parallel collector and ``write_printed_file`` records the
            joined plain-text body after a successful render (TXN-01).
            Style ESC bytes are never captured (TXN-02).
        source_path: The printed file's path, recorded in the transcript
            header. Required when ``transcript_write`` is provided.
        sleep_fn: Pacing sleep seam (see module docstring).
        cancel_check: Optional poll; True aborts with ``PrintCancelled``.

    Raises:
        ValueError: invalid ``speed_mode`` (before any driver call).
        PrintCancelled: ``cancel_check`` returned True mid-render.
    """
    from claude_teletype.printing.drivers import chunk_writes
    from claude_teletype.rendering.markdown import MarkdownRenderer
    from claude_teletype.rendering.wordwrap import WordWrapper
    from claude_teletype.transcript import write_printed_file

    if speed_mode not in ("typewriter", "instant"):
        raise ValueError(
            f"invalid speed_mode {speed_mode!r}; "
            "expected 'typewriter' or 'instant'"
        )

    columns = profile.columns if profile is not None and profile.columns else 80
    buffer_bytes = (
        profile.buffer_bytes
        if profile is not None and getattr(profile, "buffer_bytes", None)
        else 256
    )

    if speed_mode == "typewriter":
        from claude_teletype.audio import make_bell_output
        from claude_teletype.rendering.pacer import CHAR_DELAYS, classify_char

        base_delay = (base_delay_ms or 0.0) / 1000.0
        bell_fn = (lambda ch: None) if no_audio else make_bell_output()
        if sleep_fn is None:
            # Resolved late (not as an early-bound default) so tests that
            # patch time.sleep still intercept the sync CLI pacing path.
            sleep_fn = time.sleep

        def text_dest(char: str) -> None:
            driver.write(char)
            bell_fn(char)
            if base_delay > 0:
                sleep_fn(base_delay * CHAR_DELAYS[classify_char(char)])

        wrapper = WordWrapper(columns, text_dest)
        # Style bursts are tiny ESC sequences — no chunking needed.
        style_dest = driver.write_bytes
    else:
        wrapper = WordWrapper(columns, driver.write)

        def style_dest(data: bytes) -> None:
            chunk_writes(driver, data, buffer_bytes)

    # TXN-02 parallel collector: taps ONLY the text channel. Style bytes
    # never reach the transcript.
    transcript_buffer: list[str] = []
    if transcript_write is not None:
        def base_feed(char: str) -> None:
            wrapper.feed(char)
            transcript_buffer.append(char)
    else:
        base_feed = wrapper.feed

    # WR-01 between-characters cancel check: polled before each character
    # enters the wrapper, in both speed modes.
    if cancel_check is not None:
        def renderer_text_fn(char: str) -> None:
            if cancel_check():
                raise PrintCancelled()
            base_feed(char)
    else:
        renderer_text_fn = base_feed

    renderer = MarkdownRenderer(
        text_output_fn=renderer_text_fn,
        style_output_fn=style_dest,
        profile=profile,
        columns=columns,
    )
    try:
        renderer.render(text)
        # WordWrapper buffers the last word until flush(); flush BEFORE
        # end_response so the cut/eject follows every visible character.
        wrapper.flush()
        end_response = getattr(driver, "end_response", None)
        if end_response is not None:
            end_response()
        if transcript_write is not None:
            write_printed_file(
                transcript_write, source_path, "".join(transcript_buffer),
            )
    finally:
        # T-33-02: LIFO style-off bytes on EVERY exit path (success,
        # cancel, driver error) — the printer never keeps leaked emphasis.
        renderer.close()
