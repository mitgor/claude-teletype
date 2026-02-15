"""Tests for the transcript file writer output module."""

from claude_teletype.transcript import make_transcript_output


def test_make_transcript_output_returns_tuple(tmp_path):
    """make_transcript_output() returns a 2-tuple of callables."""
    write_fn, close_fn = make_transcript_output(tmp_path)
    assert callable(write_fn)
    assert callable(close_fn)
    close_fn()


def test_transcript_writes_characters(tmp_path):
    """Characters written via write_fn appear in the transcript file."""
    write_fn, close_fn = make_transcript_output(tmp_path)
    for char in "Hi\n":
        write_fn(char)
    close_fn()

    files = list(tmp_path.glob("transcript-*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "Hi\n"


def test_transcript_flushes_on_newline(tmp_path):
    """Content through newline is flushed to disk immediately."""
    write_fn, close_fn = make_transcript_output(tmp_path)
    for char in "Hello\n":
        write_fn(char)

    # Read without closing -- newline triggers flush so content should be on disk
    files = list(tmp_path.glob("transcript-*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "Hello\n"
    close_fn()


def test_transcript_close_flushes_remaining(tmp_path):
    """close_fn flushes characters that were written without a trailing newline."""
    write_fn, close_fn = make_transcript_output(tmp_path)
    for char in "partial":
        write_fn(char)
    close_fn()

    files = list(tmp_path.glob("transcript-*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "partial"


def test_transcript_creates_directory(tmp_path):
    """A non-existent transcript directory is created automatically."""
    sub = tmp_path / "deep" / "nested"
    write_fn, close_fn = make_transcript_output(sub)
    write_fn("x")
    close_fn()

    assert sub.is_dir()
    files = list(sub.glob("transcript-*.txt"))
    assert len(files) == 1


def test_transcript_filename_format(tmp_path):
    """Transcript filename matches the expected pattern."""
    write_fn, close_fn = make_transcript_output(tmp_path)
    close_fn()

    files = list(tmp_path.glob("transcript-*.txt"))
    assert len(files) == 1
    name = files[0].name
    assert name.startswith("transcript-")
    assert name.endswith(".txt")
    # Timestamp portion should be 15 chars: YYYYMMDD-HHMMSS
    timestamp_part = name[len("transcript-") : -len(".txt")]
    assert len(timestamp_part) == 15


def test_close_idempotent(tmp_path):
    """Calling close_fn multiple times does not raise."""
    write_fn, close_fn = make_transcript_output(tmp_path)
    write_fn("a")
    close_fn()
    close_fn()  # second call should not raise
