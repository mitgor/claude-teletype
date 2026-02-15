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
