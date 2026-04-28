"""Streaming markdown renderer composing with WordWrapper and ProfilePrinterDriver.

Implements MD-01..MD-08 from REQUIREMENTS.md as a hand-written state machine
(no external markdown library). The renderer has two output channels:

- text_output_fn: plain visible characters; the caller wires this into
  WordWrapper.feed() so wrapping happens downstream.
- style_output_fn: raw ESC byte sequences (bold/italic/underline);
  typically wired to ProfilePrinterDriver.write_bytes for atomic transfer.

Block parsing (MD-02..MD-06) is in this module's MarkdownRenderer class;
inline emphasis (MD-01) is added by Plan 23-03 by replacing the
``_render_inline`` stub.

Newline routing (MD-08): every newline emitted by the renderer goes through
text_output_fn("\\n"). The renderer NEVER calls style_output_fn(b"\\n").
Newlines must reach ProfilePrinterDriver.write("\\n") so the atomic
CR+LF + reinit transfer stays intact.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from claude_teletype.profiles import PrinterProfile

__all__ = ["MarkdownRenderer"]

# Module-level compiled regexes — cheap and keeps dispatch readable.
_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ULIST_ITEM = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_OLIST_ITEM = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_BLOCKQUOTE = re.compile(r"^>\s?(.*)$")
_CODE_FENCE = re.compile(r"^```\s*\S*\s*$")
_TABLE_DELIM = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


class MarkdownRenderer:
    """Hand-written streaming markdown renderer.

    Two output channels:
    - ``text_output_fn``: plain visible characters INCLUDING newlines.
      The caller wires this into ``WordWrapper.feed()`` so wrapping
      happens downstream.
    - ``style_output_fn``: raw ESC byte sequences (bold/italic/underline);
      typically wired to ``ProfilePrinterDriver.write_bytes`` for atomic
      transfer. Defaults to a no-op so the renderer can be unit-tested
      without a profile or driver.

    Block-level features (MD-02..MD-06) are implemented here. Inline
    emphasis (MD-01) is added by Plan 23-03 by replacing the
    ``_render_inline`` stub method.

    Newline routing (MD-08): every newline emitted by the renderer is
    routed through ``text_output_fn("\\n")``. The renderer NEVER passes
    a newline byte through ``style_output_fn`` — that would bypass the
    atomic CR+LF + reinit transfer in ``ProfilePrinterDriver.write``.
    """

    def __init__(
        self,
        text_output_fn: Callable[[str], None],
        style_output_fn: Callable[[bytes], None] | None = None,
        profile: PrinterProfile | None = None,
        columns: int = 80,
    ) -> None:
        self._text_output_fn = text_output_fn
        self._style_output_fn: Callable[[bytes], None] = (
            style_output_fn if style_output_fn is not None else (lambda data: None)
        )
        self._profile = profile
        # Profile's columns wins when present and non-zero; else fall back
        # to the explicit columns argument.
        if profile is not None and profile.columns:
            self._columns = profile.columns
        else:
            self._columns = columns
        # Block-state tracking
        self._in_code_block: bool = False
        self._table_buffer: list[str] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def render(self, text: str) -> None:
        """Render a markdown document through the configured output channels."""
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if self._in_code_block:
                self._handle_code_line(line)
                i += 1
                continue
            if _CODE_FENCE.match(line.strip()):
                self._in_code_block = True
                i += 1
                continue
            # GFM table: header line containing `|` followed by a delimiter line.
            if (
                "|" in line
                and i + 1 < len(lines)
                and _TABLE_DELIM.match(lines[i + 1])
            ):
                rows = [line]
                i += 2  # skip the delimiter row
                while (
                    i < len(lines)
                    and "|" in lines[i]
                    and lines[i].strip()
                ):
                    rows.append(lines[i])
                    i += 1
                self._render_table(rows)
                continue
            self._dispatch_block_line(line)
            i += 1
        self._flush_table()

    # ------------------------------------------------------------------
    # Block dispatch
    # ------------------------------------------------------------------

    def _dispatch_block_line(self, line: str) -> None:
        """Route a single non-code, non-table line to the right block renderer."""
        m = _ATX_HEADING.match(line)
        if m:
            self._render_heading(len(m.group(1)), m.group(2))
            return
        m = _BLOCKQUOTE.match(line)
        if m:
            self._render_blockquote_line(m.group(1))
            return
        m = _OLIST_ITEM.match(line)
        if m:
            self._render_olist_item(
                len(m.group(1)) // 2, m.group(2), m.group(3)
            )
            return
        m = _ULIST_ITEM.match(line)
        if m:
            self._render_ulist_item(len(m.group(1)) // 2, m.group(3))
            return
        self._render_paragraph_line(line)

    # ------------------------------------------------------------------
    # Per-block renderers
    # ------------------------------------------------------------------

    def _render_heading(self, level: int, text: str) -> None:
        """ATX heading: blank line above, text (Plan 23-03 wraps in bold), trailing blank line."""
        del level  # Reserved for future heading-level differentiation.
        self._emit_text("\n")
        # Plan 23-03: emit bold style_on bytes here via self._style_output_fn.
        self._render_inline(text)
        # Plan 23-03: emit bold style_off bytes here via self._style_output_fn.
        self._emit_text("\n\n")

    def _render_ulist_item(self, indent: int, content: str) -> None:
        """Unordered list: re-glyph dash/star/plus to ``*`` with two-space-per-level indent."""
        self._emit_text("  " * indent + "* ")
        self._render_inline(content)
        self._emit_text("\n")

    def _render_olist_item(self, indent: int, num: str, content: str) -> None:
        """Ordered list: preserve the source number with two-space-per-level indent."""
        self._emit_text("  " * indent + f"{num}. ")
        self._render_inline(content)
        self._emit_text("\n")

    def _render_blockquote_line(self, content: str) -> None:
        """Blockquote: emit ``> `` prefix + content + newline."""
        self._emit_text("> ")
        self._render_inline(content)
        self._emit_text("\n")

    def _handle_code_line(self, line: str) -> None:
        """Inside a fenced code block: literal pass-through indented 4 spaces.

        Closing fence terminates the block. No inline emphasis is applied
        (literal `*not italic*` survives), per MD-04.
        """
        stripped = line.strip()
        if _CODE_FENCE.match(stripped) or stripped == "```":
            self._in_code_block = False
            return
        # Code lines bypass inline emphasis processing (MD-04 contract).
        self._emit_text("    " + line + "\n")

    def _render_paragraph_line(self, line: str) -> None:
        """Default block: emit content + newline; blank lines pass through."""
        if not line.strip():
            self._emit_text("\n")
            return
        self._render_inline(line)
        self._emit_text("\n")

    # ------------------------------------------------------------------
    # Inline emphasis seam (replaced by Plan 23-03)
    # ------------------------------------------------------------------

    def _render_inline(self, text: str) -> None:
        """Stub for Plan 23-03 inline emphasis (bold/italic/underline).

        This plan emits each character verbatim through ``text_output_fn``.
        Plan 23-03 will replace this method with a state machine that
        recognises ``**bold**``, ``__bold__``, ``*italic*``, ``_italic_``
        and emits the corresponding ESC sequences via
        ``self._style_output_fn`` while keeping plain chars on
        ``self._text_output_fn``.
        """
        self._emit_text(text)

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------

    def _render_table(self, rows: list[str]) -> None:
        """Render a buffered GFM table as an ASCII grid.

        Cells wider than the allocated column width are truncated (no
        in-cell wrapping in v1). Each row fits within ``self._columns``.
        """
        if not rows:
            return

        # Parse rows into cells. Strip leading/trailing empty cells produced
        # by leading/trailing `|` characters.
        parsed: list[list[str]] = []
        for raw in rows:
            cells = [c.strip() for c in raw.split("|")]
            # Drop a single leading empty cell (from a leading `|`) and a
            # single trailing empty cell (from a trailing `|`).
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            parsed.append(cells)

        col_count = max(len(r) for r in parsed)
        if col_count == 0:
            return
        # Pad rows that are short on cells.
        for row in parsed:
            while len(row) < col_count:
                row.append("")

        # Allocate column widths. Account for the column separators
        # ``| `` ... ` ``: layout is `| c1 | c2 | ... | cn |` so the
        # non-cell overhead is `(col_count + 1)` `|` chars plus
        # `2 * col_count` padding spaces (one space on each side of every
        # cell). Total overhead = 3 * col_count + 1.
        overhead = 3 * col_count + 1
        usable = max(col_count, self._columns - overhead)
        base = usable // col_count
        extra = usable % col_count
        widths = [base + (1 if i < extra else 0) for i in range(col_count)]

        rule = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

        def _row_line(cells: list[str]) -> str:
            parts: list[str] = ["|"]
            for cell, w in zip(cells, widths):
                clipped = cell[:w]
                parts.append(" " + clipped.ljust(w) + " |")
            return "".join(parts)

        # Header on row 0; body on rows 1..N. Between header and body emit
        # a middle rule. Top and bottom rules bracket the whole grid.
        self._emit_text(rule + "\n")
        self._emit_text(_row_line(parsed[0]) + "\n")
        self._emit_text(rule + "\n")
        for body_row in parsed[1:]:
            self._emit_text(_row_line(body_row) + "\n")
        self._emit_text(rule + "\n")

    def _flush_table(self) -> None:
        """No-op in this implementation.

        ``render`` rendered tables eagerly via look-ahead, so there is no
        deferred buffer to flush. Stub kept as a future-extension seam for
        a streaming-mode renderer that can't peek at the next line.
        """
        return None

    # ------------------------------------------------------------------
    # Text emission helper
    # ------------------------------------------------------------------

    def _emit_text(self, text: str) -> None:
        """Emit text through ``text_output_fn`` one character at a time.

        The per-character contract preserves the streaming-friendly
        interface that downstream ``WordWrapper.feed`` expects.
        """
        for ch in text:
            self._text_output_fn(ch)
