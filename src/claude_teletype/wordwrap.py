"""Streaming character-level word wrapper.

Provides a WordWrapper class that accepts characters one at a time,
buffers the current word, and inserts newlines at word boundaries
when a word would exceed the configured line width.
"""

from __future__ import annotations

from collections.abc import Callable

__all__ = ["WordWrapper"]


class WordWrapper:
    """Streaming character-level word wrapper.

    Buffers the current word and inserts newlines at word boundaries
    when a word would exceed the configured line width.

    Characters are fed one at a time via ``feed()``. When a space or
    newline is encountered, the buffered word is flushed to the output
    function with appropriate wrapping. Call ``flush()`` at end of
    stream to emit any remaining buffered word.

    Key design:
    - Space is deferred (``pending_space``) so wrapping drops the space
      rather than leaving trailing whitespace on the previous line.
    - Words longer than ``width`` are hard-broken (forced newline when
      column reaches width).
    - Multiple consecutive spaces collapse to a single space.
    - ``max(1, value)`` prevents zero-width causing infinite loops.
    """

    def __init__(self, width: int, output_fn: Callable[[str], None]) -> None:
        self._width = max(1, width)
        self._output_fn = output_fn
        self._column = 0
        self._word_buffer: list[str] = []
        self._pending_space = False

    @property
    def width(self) -> int:
        """Current line width for wrapping."""
        return self._width

    @width.setter
    def width(self, value: int) -> None:
        """Set line width, clamped to minimum of 1."""
        self._width = max(1, value)

    def feed(self, char: str) -> None:
        """Feed a single character through the wrapper.

        Spaces trigger a word flush and set pending_space. Newlines
        flush the word, reset column, and pass through. All other
        characters are buffered.
        """
        if char == "\n":
            self._flush_word()
            self._pending_space = False
            self._output_fn("\n")
            self._column = 0
        elif char == " ":
            self._flush_word()
            if self._column > 0:
                self._pending_space = True
        else:
            self._word_buffer.append(char)

    def _flush_word(self) -> None:
        """Flush the buffered word to output, inserting wraps as needed."""
        if not self._word_buffer:
            return
        word_len = len(self._word_buffer)
        space_needed = (1 if self._pending_space else 0) + word_len

        if self._column + space_needed > self._width and self._column > 0:
            self._output_fn("\n")
            self._column = 0
            self._pending_space = False

        if self._pending_space and self._column > 0:
            self._output_fn(" ")
            self._column += 1
        self._pending_space = False

        for ch in self._word_buffer:
            if self._column >= self._width:
                self._output_fn("\n")
                self._column = 0
            self._output_fn(ch)
            self._column += 1
        self._word_buffer.clear()

    def flush(self) -> None:
        """Flush any remaining buffered word to output.

        Call this at the end of a stream to ensure the last word
        is emitted.
        """
        self._flush_word()
