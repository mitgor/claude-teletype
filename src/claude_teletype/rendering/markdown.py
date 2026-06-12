"""Streaming markdown renderer composing with WordWrapper and ProfilePrinterDriver.

Implements MD-01..MD-08 from REQUIREMENTS.md as a hand-written state machine
(no external markdown library). The renderer has two output channels:

- text_output_fn: plain visible characters; the caller wires this into
  WordWrapper.feed() so wrapping happens downstream.
- style_output_fn: raw ESC byte sequences (bold/italic/underline);
  typically wired to ProfilePrinterDriver.write_bytes for atomic transfer.

Block parsing (MD-02..MD-06) and inline emphasis (MD-01: bold via
``**``/``__``, italic via ``*``/``_``) are both implemented in
MarkdownRenderer. Inline emphasis routes through profile-aware
``resolve_style`` lookups so each profile picks its native ESC bytes
(or falls back to underline / plain text per the documented chain).

Newline routing (MD-08): every newline emitted by the renderer goes through
text_output_fn("\\n"). The renderer NEVER calls style_output_fn(b"\\n").
Newlines must reach ProfilePrinterDriver.write("\\n") so the atomic
CR+LF + reinit transfer stays intact.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from claude_teletype.printing.profiles import PrinterProfile, resolve_style

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

    Block-level features (MD-02..MD-06) and inline emphasis (MD-01:
    bold, italic) are both implemented here. Inline emphasis is a state
    machine in ``_render_inline`` that toggles ``_bold_open`` /
    ``_italic_open`` on greedy ``**``/``__`` and ``*``/``_`` markers and
    routes on/off bytes through ``_emit_style_on/off`` via
    ``resolve_style(profile, ...)``. Block-boundary close discipline
    (``_close_open_styles``) prevents emphasis from leaking across
    constructs.

    Newline routing (MD-08): every newline emitted by the renderer is
    routed through ``text_output_fn("\\n")``. The renderer NEVER passes
    a newline byte through ``style_output_fn`` — that would bypass the
    atomic CR+LF + reinit transfer in ``ProfilePrinterDriver.write``.

    Cancel safety (FLOW-05, Phase 26): callers MUST invoke ``close()``
    when aborting a render mid-stream (e.g. the user pressing the cancel
    keybinding during a print job). ``close()`` flushes any open
    bold/italic spans through ``style_output_fn`` so the printer's
    style state is clean for the next print job. Without ``close()``,
    a printer left in bold mode would render the *next* document's
    text in bold until something else cleared the state. The public
    ``close()`` method is a thin wrapper around ``_close_open_styles``
    so the LIFO close order (italic_off before bold_off) and the
    ``resolve_style`` fallback chain stay identical to the seven
    existing block-boundary close sites.
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
        # Inline-emphasis state (Plan 23-03). Tracks whether `_render_inline`
        # has an open bold or italic span from the markdown source. The
        # block-boundary close discipline (`_close_open_styles`) clears these
        # flags before any block-level newline so emphasis cannot leak across
        # block constructs (heading, list item, blockquote line, paragraph,
        # code-block enter, end-of-document).
        self._bold_open: bool = False
        self._italic_open: bool = False

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def render(self, text: str) -> None:
        """Render a markdown document through the configured output channels."""
        lines = text.split("\n")
        # ``split("\n")`` on a string ending with ``\n`` produces a trailing
        # empty element. That trailing newline is structural delimitation,
        # not a blank-line block — drop it so a one-line document like
        # "# Hello\n" doesn't render as if a blank paragraph followed.
        if lines and lines[-1] == "":
            lines.pop()
        i = 0
        while i < len(lines):
            line = lines[i]
            if self._in_code_block:
                self._handle_code_line(line)
                i += 1
                continue
            if _CODE_FENCE.match(line.strip()):
                # Defensive close on code-block entry: any inline emphasis
                # left open by a preceding paragraph cannot leak into the
                # code block (where emphasis is suppressed entirely).
                self._close_open_styles()
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
        # Document-end safety: close any unclosed emphasis (`**hello` with no
        # closing `**`) so style mode cannot leak into the next print job.
        self._close_open_styles()

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
        """ATX heading: blank line above, bold-wrapped inline text, blank below.

        The heading is wrapped in an OUTER bold pair emitted directly via
        ``_emit_style_on/off`` — independent of the inline ``_bold_open``
        state, which tracks bold spans from the markdown source itself.
        Inline emphasis inside the heading text (`# **Inner Bold**`) toggles
        `_bold_open` separately; ``_close_open_styles`` then closes any
        inline-opened spans before the heading's trailing newline.
        """
        del level  # Reserved for future heading-level differentiation.
        self._emit_text("\n")
        # Outer heading bold is independent of inline _bold_open state.
        self._emit_style_on("bold")
        self._render_inline(text)
        # Close inline emphasis FIRST (so any unclosed `**`/`*` inside the
        # heading text closes before we close the outer heading bold).
        self._close_open_styles()
        # Now close the outer heading bold pair.
        self._emit_style_off("bold")
        self._emit_text("\n\n")

    def _render_ulist_item(self, indent: int, content: str) -> None:
        """Unordered list: re-glyph dash/star/plus to ``*`` with two-space-per-level indent."""
        self._emit_text("  " * indent + "* ")
        self._render_inline(content)
        self._close_open_styles()
        self._emit_text("\n")

    def _render_olist_item(self, indent: int, num: str, content: str) -> None:
        """Ordered list: preserve the source number with two-space-per-level indent."""
        self._emit_text("  " * indent + f"{num}. ")
        self._render_inline(content)
        self._close_open_styles()
        self._emit_text("\n")

    def _render_blockquote_line(self, content: str) -> None:
        """Blockquote: emit ``> `` prefix + content + newline."""
        self._emit_text("> ")
        self._render_inline(content)
        self._close_open_styles()
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
        self._close_open_styles()
        self._emit_text("\n")

    # ------------------------------------------------------------------
    # Inline emphasis state machine (MD-01)
    # ------------------------------------------------------------------

    def _render_inline(self, text: str) -> None:
        """Render an inline span recognising bold (``**``/``__``) and italic (``*``/``_``).

        Greedy two-then-one tokenization: ``**`` and ``__`` toggle bold
        before the single-char ``*``/``_`` italic toggles. ``***foo***``
        therefore opens bold, opens italic, emits ``foo``, then the
        closing ``***`` closes italic, closes bold (state-machine LIFO
        guarantees pairing because both flags toggle independently).

        Markdown emphasis markers are state-machine tokens — they are
        consumed and never reach ``text_output_fn``. All other characters
        flow through ``self._text_output_fn`` one at a time, preserving
        the per-character streaming contract.

        Style bytes are routed via ``_emit_style_on/off`` which consult
        ``resolve_style(profile, style)`` so the renderer never branches
        on profile capabilities itself. When the profile lacks the
        capability and ``resolve_style`` returns ``(b"", b"")``, the
        emit is silently skipped and text falls back to plain.
        """
        i = 0
        n = len(text)
        while i < n:
            # Greedy: ``**`` / ``__`` (bold) wins over single ``*`` / ``_`` (italic).
            if i + 1 < n and text[i] == "*" and text[i + 1] == "*":
                self._toggle_bold()
                i += 2
                continue
            if i + 1 < n and text[i] == "_" and text[i + 1] == "_":
                self._toggle_bold()
                i += 2
                continue
            ch = text[i]
            if ch == "*" or ch == "_":
                self._toggle_italic()
                i += 1
                continue
            self._text_output_fn(ch)
            i += 1

    def _toggle_bold(self) -> None:
        """Toggle inline bold state — emit on/off bytes per resolve_style."""
        if self._bold_open:
            self._emit_style_off("bold")
            self._bold_open = False
        else:
            self._emit_style_on("bold")
            self._bold_open = True

    def _toggle_italic(self) -> None:
        """Toggle inline italic state — emit on/off bytes per resolve_style."""
        if self._italic_open:
            self._emit_style_off("italic")
            self._italic_open = False
        else:
            self._emit_style_on("italic")
            self._italic_open = True

    def _emit_style_on(self, style: str) -> None:
        """Emit ``style``'s on-bytes via the style channel, if non-empty.

        Silently no-ops when ``self._profile is None`` (renderer used
        without a profile, e.g. unit tests) or when the profile's
        ``resolve_style`` chain returns ``(b"", b"")`` (capability not
        supported and no fallback available — falls back to plain text).
        """
        if self._profile is None:
            return
        on, _off = resolve_style(self._profile, style)
        if on:
            self._style_output_fn(on)

    def _emit_style_off(self, style: str) -> None:
        """Emit ``style``'s off-bytes via the style channel, if non-empty.

        Symmetry safety: ``resolve_style`` returns the matching off pair
        for whichever capability it picked, so every off emit closes the
        same capability the corresponding on emit opened — never a
        cross-capability mix.
        """
        if self._profile is None:
            return
        _on, off = resolve_style(self._profile, style)
        if off:
            self._style_output_fn(off)

    def _close_open_styles(self) -> None:
        """Force-close any open inline emphasis before crossing a block boundary.

        Called before every newline emit at the end of a block-level
        construct (heading, list item, blockquote line, paragraph,
        code-block enter, end-of-document) so bold/italic mode does not
        leak past the markdown construct that opened it. Critical for
        printer hardware where style codes persist until explicitly
        cleared — leaking bold mode across paragraphs would taint the
        next print job.

        Closes italic before bold so the close order mirrors the typical
        open order (bold-on, italic-on -> italic-off, bold-off) for
        nested ``**outer *inner* outer**`` spans.
        """
        if self._italic_open:
            self._emit_style_off("italic")
            self._italic_open = False
        if self._bold_open:
            self._emit_style_off("bold")
            self._bold_open = False

    def close(self) -> None:
        """Public abort hook: emit style_off bytes for any open emphasis.

        Plan 26-02 (FLOW-05) public API. Callers MUST invoke this when
        aborting a render mid-stream (e.g. the user pressing the cancel
        keybinding during a print job — Plan 26-03 wires the call site
        in ``tui.py``). Emits ``italic_off`` before ``bold_off`` (LIFO,
        matching the natural nested ``**outer *inner* outer**`` open
        order) so the printer's bold/italic state is cleared when
        control returns to the caller.

        Idempotent: a second call after the flags are already cleared
        is a silent no-op. Safe to call when ``profile is None`` — the
        underlying ``_emit_style_off`` short-circuits via the
        ``self._profile is None: return`` guard inherited from Phase
        23-03.

        Implementation delegates to ``_close_open_styles`` so the seven
        existing block-boundary close sites and this public hook share
        a single source of truth for emit ordering and the
        ``resolve_style`` fallback chain. Do NOT inline the cleanup
        logic here — keep it in one place.
        """
        self._close_open_styles()

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
