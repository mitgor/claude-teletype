"""Tests for streaming word-wrap algorithm."""

from claude_teletype.wordwrap import WordWrapper


def _wrap(text: str, width: int) -> str:
    """Helper: feed text char-by-char through WordWrapper, return result."""
    collected: list[str] = []
    wrapper = WordWrapper(width, collected.append)
    for ch in text:
        wrapper.feed(ch)
    wrapper.flush()
    return "".join(collected)


class TestBasicWrapping:
    """Test 1: Basic word-boundary wrapping."""

    def test_wraps_at_word_boundaries(self) -> None:
        result = _wrap("The quick brown fox jumps over the lazy dog", 20)
        assert result == "The quick brown fox\njumps over the lazy\ndog"


class TestNoWrapNeeded:
    """Test 2: Short text fits within width."""

    def test_no_wrap_when_text_fits(self) -> None:
        result = _wrap("Hello", 20)
        assert result == "Hello"


class TestExactFit:
    """Test 3: Text fits exactly at width boundary."""

    def test_exact_fit_no_wrap(self) -> None:
        result = _wrap("abcde fghij", 11)
        assert result == "abcde fghij"


class TestWordBoundaryWrap:
    """Test 4: Wrap at word boundary when next word exceeds width."""

    def test_wraps_when_word_exceeds_width(self) -> None:
        result = _wrap("abcde fghij klmno", 11)
        assert result == "abcde fghij\nklmno"


class TestLongWordHardBreak:
    """Test 5: Words longer than width are hard-broken."""

    def test_hard_break_long_word(self) -> None:
        result = _wrap("abcdefghijklmno", 10)
        assert result == "abcdefghij\nklmno"


class TestExplicitNewlinePassthrough:
    """Test 6: Explicit newlines in input pass through unchanged."""

    def test_newline_passthrough(self) -> None:
        result = _wrap("hello\nworld", 20)
        assert result == "hello\nworld"


class TestExplicitNewlineResetsColumn:
    """Test 7: Explicit newline resets column counter."""

    def test_newline_resets_column(self) -> None:
        result = _wrap("hello\n" + "a" * 20 + " next", 20)
        assert result == "hello\n" + "a" * 20 + "\nnext"


class TestDeferredSpaceNoTrailing:
    """Test 8: No trailing whitespace on wrapped lines."""

    def test_no_trailing_space(self) -> None:
        result = _wrap("hello world", 5)
        assert result == "hello\nworld"


class TestMultipleSpacesCollapse:
    """Test 9: Multiple consecutive spaces collapse to one."""

    def test_spaces_collapse(self) -> None:
        result = _wrap("hello  world", 20)
        assert result == "hello world"


class TestFlushEmitsBufferedWord:
    """Test 10: flush() emits any remaining buffered word."""

    def test_flush_emits_word(self) -> None:
        collected: list[str] = []
        wrapper = WordWrapper(20, collected.append)
        for ch in "hello world":
            wrapper.feed(ch)
        # Without flush, "world" is still buffered
        wrapper.flush()
        assert "".join(collected) == "hello world"


class TestMutableWidth:
    """Test 11: Width can be changed mid-stream."""

    def test_width_change_takes_effect(self) -> None:
        collected: list[str] = []
        wrapper = WordWrapper(20, collected.append)
        # Feed first part at width 20
        for ch in "hello ":
            wrapper.feed(ch)
        # Change width to 10
        wrapper.width = 10
        # Feed remaining text that should wrap at width 10
        for ch in "world abcde fghij":
            wrapper.feed(ch)
        wrapper.flush()
        result = "".join(collected)
        # "hello" flushed at space, then width changed to 10
        # "world" fits (col 5 + 1 space + 5 = 11 > 10) -> wrap
        # "abcde" fits on new line (5 chars)
        # "fghij" (col 5 + 1 + 5 = 11 > 10) -> wrap
        assert result == "hello\nworld\nabcde\nfghij"


class TestWidthMinimumClamp:
    """Test 12: Width is clamped to minimum of 1."""

    def test_width_zero_clamped_to_one(self) -> None:
        wrapper = WordWrapper(0, lambda _: None)
        assert wrapper.width == 1

    def test_width_negative_clamped_to_one(self) -> None:
        wrapper = WordWrapper(-5, lambda _: None)
        assert wrapper.width == 1

    def test_width_setter_clamps(self) -> None:
        wrapper = WordWrapper(10, lambda _: None)
        wrapper.width = 0
        assert wrapper.width == 1


class TestEmptyInput:
    """Test 13: Empty input produces no output."""

    def test_empty_feed_and_flush(self) -> None:
        collected: list[str] = []
        wrapper = WordWrapper(20, collected.append)
        wrapper.flush()
        assert collected == []


class TestLeadingSpaceIgnored:
    """Test 14: Leading space at start of line is ignored."""

    def test_leading_space_dropped(self) -> None:
        result = _wrap(" hello", 20)
        assert result == "hello"
