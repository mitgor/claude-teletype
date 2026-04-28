"""Tests for the transcript file writer output module."""

from pathlib import Path

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


class TestWritePrintedFile:
    """Plan 26-03 (TXN-01..TXN-03): transcript.write_printed_file helper."""

    def test_write_fn_none_is_noop(self, tmp_path):
        """TXN-03: write_fn=None means no transcript configured -> no-op."""
        from claude_teletype.transcript import write_printed_file

        # Must not raise. No way to observe; the assertion is "doesn't crash".
        write_printed_file(None, tmp_path / "x.md", "body")

    def test_writes_header_and_body(self, tmp_path):
        from claude_teletype.transcript import write_printed_file

        captured: list[str] = []
        md = tmp_path / "doc.md"
        md.write_text("# Doc\n")
        write_printed_file(captured.append, md, "Body text")
        joined = "".join(captured)
        assert joined.startswith("Printed file: ")
        assert str(md.resolve()) in joined
        assert "Body text" in joined
        assert joined.endswith("\n")

    def test_relative_path_becomes_absolute(self, tmp_path, monkeypatch):
        from claude_teletype.transcript import write_printed_file

        monkeypatch.chdir(tmp_path)
        rel = Path("doc.md")
        (tmp_path / "doc.md").write_text("hello")
        captured: list[str] = []
        write_printed_file(captured.append, rel, "")
        joined = "".join(captured)
        # Absolute path should appear (resolves via tmp_path/doc.md)
        assert str((tmp_path / "doc.md").resolve()) in joined

    def test_empty_body(self, tmp_path):
        from claude_teletype.transcript import write_printed_file

        captured: list[str] = []
        write_printed_file(captured.append, tmp_path / "x.md", "")
        joined = "".join(captured)
        # "Printed file: <path>\n" + "" + "\n" => trailing \n still emitted
        assert joined.endswith("\n\n")

    def test_multi_line_body_preserved_verbatim(self, tmp_path):
        from claude_teletype.transcript import write_printed_file

        captured: list[str] = []
        body = "Line 1\nLine 2\nLine 3"
        write_printed_file(captured.append, tmp_path / "x.md", body)
        joined = "".join(captured)
        assert "Line 1\nLine 2\nLine 3" in joined

    def test_per_char_streaming(self, tmp_path):
        """write_fn is called once per character (matches transcript convention)."""
        from claude_teletype.transcript import write_printed_file

        captured: list[str] = []
        md = tmp_path / "x.md"
        md.touch()
        write_printed_file(captured.append, md, "abc")
        # Each captured element is a single char (per-char contract)
        assert all(len(c) == 1 for c in captured)
        # Reassembly equals the formatted string
        assert "".join(captured) == f"Printed file: {md.resolve()}\nabc\n"
