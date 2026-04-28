"""Tests for streaming markdown renderer (block-level features MD-02..MD-08).

Inline emphasis (MD-01) is added by Plan 23-03 and tested there.
"""

from claude_teletype.markdown import MarkdownRenderer
from claude_teletype.wordwrap import WordWrapper


def _render(text: str, columns: int = 80) -> str:
    """Helper: render ``text`` and return the joined text-channel output."""
    collected: list[str] = []
    renderer = MarkdownRenderer(collected.append, columns=columns)
    renderer.render(text)
    return "".join(collected)


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
