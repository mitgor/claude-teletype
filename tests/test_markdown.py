"""Tests for streaming markdown renderer.

Block-level features (MD-02..MD-08) landed in Plan 23-02; inline
emphasis (MD-01: bold + italic with profile-aware ``resolve_style``
fallback chain) landed in Plan 23-03 and is exercised by the
``TestInlineEmphasis``, ``TestStyleFallback``, ``TestSymmetrySafety``,
and ``TestIntegration`` classes at the bottom of this file.
"""

from claude_teletype.markdown import MarkdownRenderer
from claude_teletype.profiles import get_profile
from claude_teletype.wordwrap import WordWrapper


def _render(text: str, columns: int = 80) -> str:
    """Helper: render ``text`` and return the joined text-channel output."""
    collected: list[str] = []
    renderer = MarkdownRenderer(collected.append, columns=columns)
    renderer.render(text)
    return "".join(collected)


def _render_with_profile(
    text: str,
    profile_name: str = "escp",
    columns: int = 80,
) -> tuple[str, list[bytes]]:
    """Helper: render ``text`` against a built-in profile and capture both channels.

    Returns ``(joined_text_output, style_calls)`` where ``style_calls`` is
    the chronological list of byte chunks delivered to ``style_output_fn``.
    """
    text_calls: list[str] = []
    style_calls: list[bytes] = []
    renderer = MarkdownRenderer(
        text_calls.append,
        style_output_fn=style_calls.append,
        profile=get_profile(profile_name),
        columns=columns,
    )
    renderer.render(text)
    return "".join(text_calls), style_calls


class TestHeadings:
    """MD-02: ATX headings (#..######)."""

    def test_h1_emits_blank_line_above_and_below(self) -> None:
        assert _render("# Hello\n") == "\nHello\n\n"

    def test_h6_strips_six_hashes(self) -> None:
        assert _render("###### Six\n") == "\nSix\n\n"

    def test_heading_strips_trailing_hashes(self) -> None:
        assert _render("# Hello ###\n") == "\nHello\n\n"

    def test_heading_with_no_space_treated_as_paragraph(self) -> None:
        # No space after # → not a heading per ATX rules.
        assert _render("###no-space\n") == "###no-space\n"

    def test_seven_hashes_treated_as_paragraph(self) -> None:
        # Max heading level is 6; seven hashes degrade to paragraph.
        assert _render("####### Seven\n") == "####### Seven\n"


class TestLists:
    """MD-03: Lists (unordered + ordered, nested)."""

    def test_unordered_list_dash(self) -> None:
        assert _render("- one\n- two\n") == "* one\n* two\n"

    def test_unordered_list_asterisk(self) -> None:
        assert _render("* one\n") == "* one\n"

    def test_unordered_list_plus(self) -> None:
        assert _render("+ one\n") == "* one\n"

    def test_nested_list_two_space_indent(self) -> None:
        assert _render("- top\n  - nested\n") == "* top\n  * nested\n"

    def test_ordered_list_preserves_numbers(self) -> None:
        assert _render("1. first\n2. second\n") == "1. first\n2. second\n"


class TestCodeBlocks:
    """MD-04: Fenced code blocks (```...```)."""

    def test_code_block_indents_four_spaces(self) -> None:
        src = "```\nx = 1\n```\n"
        assert _render(src) == "    x = 1\n"

    def test_code_block_emphasis_passes_through_literally(self) -> None:
        # No inline emphasis processing inside code blocks (MD-04).
        src = "```\n*not italic*\n```\n"
        assert _render(src) == "    *not italic*\n"

    def test_code_block_language_tag_ignored(self) -> None:
        src = "```python\nfoo\n```\n"
        assert _render(src) == "    foo\n"

    def test_code_block_multiline_indents_each_line(self) -> None:
        # Each line inside the fence is independently indented 4 spaces;
        # blank lines inside the block survive as empty indented lines.
        src = "```\nline one\nline two\n```\n"
        assert _render(src) == "    line one\n    line two\n"


class TestBlockquotes:
    """MD-05: Blockquotes (`> ` prefix)."""

    def test_blockquote_emits_marker_prefix(self) -> None:
        assert _render("> hello\n") == "> hello\n"

    def test_blockquote_strips_one_space_after_marker(self) -> None:
        # `>hello` → renderer normalizes to `> hello` (canonical prefix).
        assert _render(">hello\n") == "> hello\n"


class TestTables:
    """MD-06: GFM tables rendered as ASCII grids."""

    def test_simple_two_column_table(self) -> None:
        src = "|A|B|\n|---|---|\n|1|2|\n"
        out = _render(src, columns=20)
        # Structural assertions — ASCII grid characters and content survive.
        assert "+" in out
        assert "|" in out
        assert "A" in out and "B" in out
        assert "1" in out and "2" in out
        # Three horizontal rules (top, middle, bottom) × at least 2 `+`s
        # per rule = at least 6 `+` characters.
        assert out.count("+") >= 6

    def test_table_fits_within_columns(self) -> None:
        # Cells longer than allocated width must be truncated so each row fits.
        wide = "x" * 100
        src = f"|{wide}|{wide}|\n|---|---|\n|y|z|\n"
        out = _render(src, columns=30)
        for line in out.split("\n"):
            assert len(line) <= 30, f"line {line!r} exceeds columns=30"


class TestWordWrapperComposition:
    """MD-07: rendered output flows cleanly through a real WordWrapper(80)."""

    def test_renderer_composes_with_real_wordwrapper(self) -> None:
        collected: list[str] = []
        wrapper = WordWrapper(80, collected.append)
        renderer = MarkdownRenderer(wrapper.feed, columns=80)
        src = (
            "# Title\n"
            "\n"
            "First paragraph here.\n"
            "\n"
            "- item one\n"
            "- item two\n"
            "\n"
            "> a quote line\n"
            "\n"
            "```\n"
            "code line\n"
            "```\n"
        )
        renderer.render(src)
        wrapper.flush()
        out = "".join(collected)
        # Structural elements with non-space leading chars survive WordWrapper:
        # heading text, paragraph, list bullets (`* ...`), blockquote (`> ...`),
        # and code-block content.
        assert "Title" in out
        assert "First paragraph here." in out
        assert "* item one" in out
        assert "* item two" in out
        assert "> a quote line" in out
        # Note: code-block 4-space leading indent is stripped by WordWrapper's
        # leading-space-at-column-0 rule (canonical wrap behavior — see
        # tests/test_wordwrap.py::TestLeadingSpaceIgnored). The code-line text
        # itself still survives, just unindented after the wrap stage.
        assert "code line" in out
        # MD-07 enforced: WordWrapper kept every line within 80 chars.
        for line in out.split("\n"):
            assert len(line) <= 80, f"line {line!r} exceeds 80"

    def test_long_paragraph_wraps_at_word_boundary(self) -> None:
        # MD-07 wrap-mid-paragraph case: a paragraph longer than the column
        # width gets soft-wrapped by WordWrapper at word boundaries.
        collected: list[str] = []
        wrapper = WordWrapper(20, collected.append)
        renderer = MarkdownRenderer(wrapper.feed, columns=20)
        renderer.render(
            "The quick brown fox jumps over the lazy dog and runs away\n"
        )
        wrapper.flush()
        out = "".join(collected)
        for line in out.split("\n"):
            assert len(line) <= 20, f"line {line!r} exceeds 20"


class TestNewlineRouting:
    """MD-08: newlines route exclusively through text_output_fn."""

    def test_renderer_emits_newlines_through_text_channel(self) -> None:
        # Heading newlines reach text_output_fn as '\n' chars.
        text_calls: list[str] = []
        renderer = MarkdownRenderer(text_calls.append)
        renderer.render("# Hi\n")
        joined = "".join(text_calls)
        assert "\n" in joined
        # Blank-line above + heading newline + blank-line below = 3 newlines;
        # the contract requires at least 2.
        assert joined.count("\n") >= 2

    def test_renderer_never_emits_newline_through_style_channel(self) -> None:
        # style_output_fn must NEVER receive newline bytes (MD-08 boundary).
        text_calls: list[str] = []
        style_calls: list[bytes] = []
        renderer = MarkdownRenderer(
            text_calls.append, style_output_fn=style_calls.append
        )
        renderer.render(
            "# Title\n\n**bold** text and *italic* text.\n\n> quote\n"
        )
        # Plan 23-03 may emit style bytes here; this plan's stub emits none.
        # Either way, no style call may contain '\n'.
        for chunk in style_calls:
            assert b"\n" not in chunk, (
                f"style channel emitted newline: {chunk!r}"
            )


class TestInlineEmphasis:
    """MD-01: bold (`**`/`__`) + italic (`*`/`_`) recognition and ESC byte emission."""

    def test_double_asterisk_emits_bold_codes(self) -> None:
        text, style = _render_with_profile("**bold** here\n")
        assert "bold" in text
        # Markers are state-machine tokens, NOT text — `**` does not survive.
        assert "**" not in text
        # escp profile: bold_on = ESC E (b"\x1bE"), bold_off = ESC F (b"\x1bF").
        assert b"\x1bE" in style
        assert b"\x1bF" in style
        # bold_on appears before bold_off in the call sequence.
        assert style.index(b"\x1bE") < style.index(b"\x1bF")

    def test_double_underscore_emits_bold_codes(self) -> None:
        text, style = _render_with_profile("__bold__\n")
        assert "bold" in text
        assert "__" not in text
        assert b"\x1bE" in style and b"\x1bF" in style

    def test_single_asterisk_emits_italic_codes(self) -> None:
        text, style = _render_with_profile("*italic* here\n")
        assert "italic" in text
        assert "*italic*" not in text
        # escp profile: italic_on = ESC 4 (b"\x1b4"), italic_off = ESC 5 (b"\x1b5").
        assert b"\x1b4" in style and b"\x1b5" in style
        assert style.index(b"\x1b4") < style.index(b"\x1b5")

    def test_single_underscore_emits_italic_codes(self) -> None:
        text, style = _render_with_profile("_italic_\n")
        assert "italic" in text
        assert "_italic_" not in text
        assert b"\x1b4" in style and b"\x1b5" in style

    def test_emphasis_markers_stripped_from_text(self) -> None:
        # Pure paragraph (no list/blockquote/table chars) so we can
        # straightforwardly assert no `*` or `_` survives the state machine.
        text, _style = _render_with_profile("**a** and *b*\n")
        assert "a" in text and "b" in text
        assert text.count("*") == 0
        assert text.count("_") == 0

    def test_nested_bold_inside_italic(self) -> None:
        text, style = _render_with_profile("*outer **inner** outer*\n")
        # Visible text retains spacing around the inner bold span.
        assert "outer inner outer" in text
        # Sequence: italic_on, bold_on, bold_off, italic_off (paragraph close
        # is symmetric — every `*` and `**` toggles its own flag).
        i_on = style.index(b"\x1b4")
        b_on = style.index(b"\x1bE")
        b_off = style.index(b"\x1bF")
        i_off = style.index(b"\x1b5")
        assert i_on < b_on < b_off < i_off

    def test_bold_closes_before_line_newline(self) -> None:
        # `**bold**\n`: paragraph closes the bold span via paired toggle, and
        # the block-boundary `_close_open_styles()` runs as a no-op (already
        # closed). One bold-on / one bold-off in the trace.
        _text, style = _render_with_profile("**bold**\n")
        assert style.count(b"\x1bE") == 1
        assert style.count(b"\x1bF") == 1

    def test_unclosed_emphasis_at_eof_closes_defensively(self) -> None:
        # No closing `**`: the renderer's defensive close at end-of-render
        # MUST still emit bold_off so the printer doesn't carry bold mode
        # into the next print job.
        _text, style = _render_with_profile("**unclosed text")
        assert style.count(b"\x1bE") == 1
        assert style.count(b"\x1bF") == 1


class TestStyleFallback:
    """MD-01 fallback chain: bold/italic substitute underline when capability is empty."""

    def test_juki_bold_falls_back_to_underline(self) -> None:
        # juki-6100: bold_on=b"" italic_on=b"" underline_on=b"\x1b-\x01".
        # `**bold**` triggers resolve_style("bold") -> underline pair.
        text, style = _render_with_profile("**bold**\n", profile_name="juki-6100")
        assert "bold" in text
        # Underline codes (NOT Epson bold codes) emitted via fallback.
        assert b"\x1b-\x01" in style
        assert b"\x1b-\x00" in style
        # And NOT the Epson bold codes — Juki has no bold_on bytes.
        assert b"\x1bE" not in style
        assert b"\x1bF" not in style

    def test_juki_italic_falls_back_to_underline(self) -> None:
        text, style = _render_with_profile("*italic*\n", profile_name="juki-6100")
        assert "italic" in text
        assert b"\x1b-\x01" in style and b"\x1b-\x00" in style
        # No italic ESC bytes (Juki has no italic_on).
        assert b"\x1b4" not in style and b"\x1b5" not in style

    def test_generic_emits_no_style_calls(self) -> None:
        # generic profile has all-empty style codes — resolve_style returns
        # (b"", b"") for every style; no emit fires.
        text, style = _render_with_profile(
            "**bold** and *italic*\n", profile_name="generic"
        )
        assert "bold" in text and "italic" in text
        assert style == []

    def test_no_profile_emits_no_style_calls(self) -> None:
        # __init__ default profile=None: _emit_style_on/off short-circuit
        # before consulting resolve_style.
        text_calls: list[str] = []
        style_calls: list[bytes] = []
        r = MarkdownRenderer(
            text_calls.append, style_output_fn=style_calls.append, profile=None
        )
        r.render("**bold** and *italic*\n")
        assert style_calls == []
        # Text channel still receives the visible chars.
        joined = "".join(text_calls)
        assert "bold" in joined and "italic" in joined


class TestSymmetrySafety:
    """Every style_on emit has a matching style_off — no leaked styles."""

    def test_every_bold_on_has_matching_bold_off(self) -> None:
        # Three independent bold spans in a single paragraph.
        _text, style = _render_with_profile(
            "**one** and **two** and **three**\n"
        )
        assert style.count(b"\x1bE") == style.count(b"\x1bF") == 3

    def test_every_italic_on_has_matching_italic_off(self) -> None:
        _text, style = _render_with_profile(
            "*one* and *two* and *three*\n"
        )
        assert style.count(b"\x1b4") == style.count(b"\x1b5") == 3

    def test_emphasis_in_heading_pairs_correctly(self) -> None:
        # The heading wraps its content in OUTER bold (1 pair) plus the
        # inline `**...**` is its own toggled pair (1 pair) — total 2 of
        # each. Either way, on/off counts MUST match so no bold mode
        # leaks past the heading.
        _text, style = _render_with_profile("# **Bold Heading**\n")
        assert style.count(b"\x1bE") == style.count(b"\x1bF")
        assert style.count(b"\x1bE") >= 1  # at least the outer heading bold

    def test_unclosed_emphasis_doesnt_leak(self) -> None:
        # Defensive close at EOF: `**leak attempt` opens bold; renderer
        # force-closes at end of render so bold mode doesn't leak.
        _text, style = _render_with_profile("**leak attempt")
        assert style.count(b"\x1bE") == style.count(b"\x1bF") == 1


class TestIntegration:
    """End-to-end gate proving MD-01..MD-08 compose correctly through the real pipeline."""

    def test_full_markdown_document_through_real_wordwrapper_with_escp_profile(
        self,
    ) -> None:
        sample = (
            "# Markdown Test\n"
            "\n"
            "First paragraph with **bold** and *italic* text.\n"
            "\n"
            "- first item with **emphasis**\n"
            "- second item plain\n"
            "\n"
            "> a quote with *italic* span\n"
            "\n"
            "```\n"
            "code with *no italic*\n"
            "```\n"
            "\n"
            "| Col1 | Col2 |\n"
            "|------|------|\n"
            "| a    | b    |\n"
        )

        text_collected: list[str] = []
        style_collected: list[bytes] = []
        wrapper = WordWrapper(80, text_collected.append)
        renderer = MarkdownRenderer(
            wrapper.feed,
            style_output_fn=style_collected.append,
            profile=get_profile("escp"),
            columns=80,
        )
        renderer.render(sample)
        wrapper.flush()
        text = "".join(text_collected)

        # ----- Text channel: structural elements survive -----
        # MD-02 heading: visible text without the leading `#`.
        assert "Markdown Test" in text
        # MD-01 marker stripping: paragraph with bold + italic markers.
        assert "First paragraph with bold and italic text." in text
        # MD-03 unordered list with `* ` glyph; emphasis markers stripped.
        assert "* first item with emphasis" in text
        assert "* second item plain" in text
        # MD-05 blockquote with italic markers stripped.
        assert "> a quote with italic span" in text
        # MD-04 boundary: emphasis inside the code block survives literally.
        # (Note: the 4-space code-block indent is intentionally stripped by
        # WordWrapper's leading-space-at-column-0 rule — see 23-02 SUMMARY
        # decision; the literal `*no italic*` content is what matters here.)
        assert "code with *no italic*" in text
        # MD-06 ASCII grid with `+` / `|` / `-` chars and the cell content.
        assert "Col1" in text and "Col2" in text
        assert "+" in text and "|" in text
        # MD-07: WordWrapper kept every line within 80 chars.
        for line in text.split("\n"):
            assert len(line) <= 80, f"line {line!r} exceeds 80"

        # ----- Style channel: escp emphasis bytes -----
        # 3 bold pairs expected: outer heading bold + paragraph `**bold**` +
        # list-item `**emphasis**`.
        assert style_collected.count(b"\x1bE") == 3
        assert style_collected.count(b"\x1bF") == 3
        # 2 italic pairs expected: paragraph `*italic*` + blockquote
        # `*italic*`. The `*no italic*` inside the code block must NOT
        # generate a third pair (MD-04 emphasis-suppression boundary).
        assert style_collected.count(b"\x1b4") == 2
        assert style_collected.count(b"\x1b5") == 2
        # MD-08: no chunk in the style channel ever contains a newline byte.
        for chunk in style_collected:
            assert b"\n" not in chunk, (
                f"style channel emitted newline: {chunk!r}"
            )


class TestRendererCancelSafety:
    """Plan 26-02 (FLOW-05): MarkdownRenderer.close() cancel-safety contract.

    Verifies the public abort hook that lets cancel handlers (Plan 26-03's
    cancel keybinding in tui.py) flush any open bold/italic spans through
    the style channel so the printer's style state is clean for the next
    print job. close() is a thin public wrapper around the existing
    private ``_close_open_styles`` helper from Phase 23-03 — single
    source of truth for emit ordering (italic_off before bold_off, LIFO).
    """

    def test_close_is_public_method(self) -> None:
        """close() is a public attribute on MarkdownRenderer."""
        assert hasattr(MarkdownRenderer, "close")
        assert callable(MarkdownRenderer.close)

    def test_close_with_open_bold_emits_bold_off(self) -> None:
        """Open bold span gets closed by close() — leaves printer state clean."""
        style_bytes: list[bytes] = []
        renderer = MarkdownRenderer(
            text_output_fn=lambda c: None,
            style_output_fn=style_bytes.append,
            profile=get_profile("escp"),
        )
        # Simulate partial render that opened bold but did not close it.
        renderer._bold_open = True
        renderer.close()
        assert b"\x1bF" in style_bytes  # ESC F = escp bold off
        assert renderer._bold_open is False

    def test_close_with_open_italic_emits_italic_off(self) -> None:
        """Open italic span gets closed by close() — leaves printer state clean."""
        style_bytes: list[bytes] = []
        renderer = MarkdownRenderer(
            text_output_fn=lambda c: None,
            style_output_fn=style_bytes.append,
            profile=get_profile("escp"),
        )
        renderer._italic_open = True
        renderer.close()
        assert b"\x1b5" in style_bytes  # ESC 5 = escp italic off
        assert renderer._italic_open is False

    def test_close_emits_italic_before_bold_lifo(self) -> None:
        """Both flags open: close() emits italic_off then bold_off (LIFO)."""
        style_bytes: list[bytes] = []
        renderer = MarkdownRenderer(
            text_output_fn=lambda c: None,
            style_output_fn=style_bytes.append,
            profile=get_profile("escp"),
        )
        renderer._bold_open = True
        renderer._italic_open = True
        renderer.close()
        # LIFO close order: italic_off (\x1b5) then bold_off (\x1bF).
        italic_idx = style_bytes.index(b"\x1b5")
        bold_idx = style_bytes.index(b"\x1bF")
        assert italic_idx < bold_idx
        assert renderer._italic_open is False
        assert renderer._bold_open is False

    def test_close_with_no_open_styles_is_noop(self) -> None:
        """No open emphasis -> close() emits nothing."""
        style_bytes: list[bytes] = []
        renderer = MarkdownRenderer(
            text_output_fn=lambda c: None,
            style_output_fn=style_bytes.append,
            profile=get_profile("escp"),
        )
        # Both flags False (default __init__ state).
        renderer.close()
        assert style_bytes == []

    def test_close_is_idempotent(self) -> None:
        """Second close() call after flags are clear emits nothing."""
        style_bytes: list[bytes] = []
        renderer = MarkdownRenderer(
            text_output_fn=lambda c: None,
            style_output_fn=style_bytes.append,
            profile=get_profile("escp"),
        )
        renderer._bold_open = True
        renderer.close()
        first_call_bytes = list(style_bytes)
        style_bytes.clear()
        renderer.close()
        # Second call should add nothing — flags already cleared.
        assert style_bytes == []
        # First call did emit bold_off.
        assert b"\x1bF" in first_call_bytes

    def test_close_with_profile_none_is_safe(self) -> None:
        """profile=None: _emit_style_off short-circuits, close() stays a no-op."""
        style_bytes: list[bytes] = []
        renderer = MarkdownRenderer(
            text_output_fn=lambda c: None,
            style_output_fn=style_bytes.append,
            profile=None,
        )
        renderer._bold_open = True
        renderer._italic_open = True
        renderer.close()  # MUST NOT raise
        # No bytes emitted — profile=None short-circuit in _emit_style_off.
        assert style_bytes == []

    def test_close_docstring_documents_abort_contract(self) -> None:
        """Docstring contract: must mention 'abort' or 'cancel' so future
        maintainers find the public API documenting Phase 26 cancel handling."""
        doc = (MarkdownRenderer.close.__doc__ or "").lower()
        assert "abort" in doc or "cancel" in doc

    def test_close_with_render_then_cancel_balances_style_byte_pairs(self) -> None:
        """End-to-end-ish: partial render emits style_on, close() balances it.

        Verifies the user-facing FLOW-05 promise: every style_on has a
        matching style_off after close() runs.
        """
        style_bytes: list[bytes] = []
        renderer = MarkdownRenderer(
            text_output_fn=lambda c: None,
            style_output_fn=style_bytes.append,
            profile=get_profile("escp"),
        )
        # Partial render: open bold (e.g. "**hello" with no closing **).
        # We synthesise this via _toggle_bold so the test doesn't depend on
        # render() internals.
        renderer._toggle_bold()  # opens bold: emits ESC E
        # Simulate user cancel: caller invokes close().
        renderer.close()
        # Byte-level balance check: bold_on (\x1bE) and bold_off (\x1bF) match.
        bold_on_count = style_bytes.count(b"\x1bE")
        bold_off_count = style_bytes.count(b"\x1bF")
        assert bold_on_count == bold_off_count == 1
