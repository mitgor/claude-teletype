"""Transcript file writer output destination.

Writes each streamed character to a timestamped transcript file,
flushing on newlines for real-time persistence.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path


def make_transcript_output(
    transcript_dir: Path | None = None,
) -> tuple[Callable[[str], None], Callable[[], None]]:
    """Create an output function that writes characters to a transcript file.

    Characters are accumulated and flushed to disk on each newline. The
    transcript file is created immediately in the given directory with a
    timestamped name.

    Args:
        transcript_dir: Directory for transcript files. Created if it does
            not exist. Defaults to ``Path.cwd() / "transcripts"``.

    Returns:
        A ``(write_fn, close_fn)`` tuple. ``write_fn`` accepts a single
        character and writes it to the transcript file. ``close_fn`` flushes
        any remaining buffered content and closes the file handle.
    """
    if transcript_dir is None:
        transcript_dir = Path.cwd() / "transcripts"

    transcript_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filepath = transcript_dir / f"transcript-{timestamp}.txt"

    fh = open(filepath, "a", encoding="utf-8")  # noqa: SIM115

    def write_fn(char: str) -> None:
        fh.write(char)
        if char == "\n":
            fh.flush()

    def close_fn() -> None:
        if not fh.closed:
            fh.flush()
            fh.close()

    return write_fn, close_fn


def write_printed_file(
    write_fn: Callable[[str], None] | None,
    path: Path,
    body: str,
) -> None:
    """Append a 'Printed file: ...' entry to the active session transcript.

    Phase 26 (TXN-01..TXN-03): wired into the TUI picker -> renderer ->
    transcript pipeline AND the CLI print -> renderer -> transcript
    pipeline. The header line records exactly which file was printed
    (absolute path resolved via Path(path).resolve()), followed by the
    rendered plain-text body.

    TXN-02: callers must pass a plain-text body — style ESC bytes are
    filtered upstream by routing the renderer's text channel through a
    parallel collector and feeding ONLY the collected text here. This
    function does NOT inspect the body content for ESC bytes; it
    streams whatever it receives.

    TXN-03: write_fn=None is a defensive no-op so callers (TUI chat
    session with no transcript_dir, CLI print without a transcript)
    can pass through without conditional checks at every call site.

    Args:
        write_fn: Per-character writer (matches make_transcript_output's
            contract). None = no transcript configured -> no-op.
        path: The printed file's path. Always rendered as absolute resolved.
        body: The plain-text rendered body (post-MarkdownRenderer text channel).

    Returns:
        None. Writes through write_fn synchronously, char by char.
    """
    if write_fn is None:
        return
    abs_path = Path(path).resolve()
    header = f"Printed file: {abs_path}\n"
    for ch in header:
        write_fn(ch)
    for ch in body:
        write_fn(ch)
    write_fn("\n")
