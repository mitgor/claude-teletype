"""Tests for the character pacing module."""

from unittest.mock import AsyncMock, patch

import pytest

from claude_teletype.pacer import CHAR_DELAYS, classify_char, pace_characters


class TestClassifyChar:
    """Tests for classify_char function."""

    @pytest.mark.parametrize("char", list(".,!?;:"))
    def test_punctuation(self, char: str) -> None:
        assert classify_char(char) == "punctuation"

    def test_newline(self) -> None:
        assert classify_char("\n") == "newline"

    def test_space(self) -> None:
        assert classify_char(" ") == "space"

    @pytest.mark.parametrize("char", list("abcXYZ0123456789@#$%^&*()[]{}|\\/<>~`"))
    def test_default(self, char: str) -> None:
        assert classify_char(char) == "default"

    def test_tab_is_default(self) -> None:
        assert classify_char("\t") == "default"

    def test_unicode_is_default(self) -> None:
        assert classify_char("\u00e9") == "default"


class TestPaceCharacters:
    """Tests for pace_characters async function."""

    @pytest.mark.asyncio
    async def test_calls_output_fn_per_character(self) -> None:
        """output_fn is called once per character, in order."""
        collected: list[str] = []
        text = "Hi!"

        with patch("claude_teletype.pacer.asyncio.sleep", new_callable=AsyncMock):
            await pace_characters(text, output_fn=collected.append)

        assert collected == ["H", "i", "!"]

    @pytest.mark.asyncio
    async def test_output_fn_preserves_order(self) -> None:
        """Characters including spaces and newlines are output in order."""
        collected: list[str] = []
        text = "a b\nc"

        with patch("claude_teletype.pacer.asyncio.sleep", new_callable=AsyncMock):
            await pace_characters(text, output_fn=collected.append)

        assert collected == ["a", " ", "b", "\n", "c"]

    @pytest.mark.asyncio
    async def test_correct_delays_applied(self) -> None:
        """asyncio.sleep is called with correct delay for each character class."""
        text = "a .!\n "
        base_ms = 75.0
        base_s = base_ms / 1000.0

        expected_delays = [
            base_s * CHAR_DELAYS["default"],  # 'a'
            base_s * CHAR_DELAYS["space"],  # ' '
            base_s * CHAR_DELAYS["punctuation"],  # '.'
            base_s * CHAR_DELAYS["punctuation"],  # '!'
            base_s * CHAR_DELAYS["newline"],  # '\n'
            base_s * CHAR_DELAYS["space"],  # ' '
        ]

        with patch("claude_teletype.pacer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await pace_characters(text, base_delay_ms=base_ms, output_fn=lambda c: None)

        assert mock_sleep.call_count == len(text)
        for i, call in enumerate(mock_sleep.call_args_list):
            assert call.args[0] == pytest.approx(expected_delays[i]), (
                f"Char {i} ({text[i]!r}): expected {expected_delays[i]}, got {call.args[0]}"
            )

    @pytest.mark.asyncio
    async def test_relative_delay_ordering(self) -> None:
        """Punctuation > default > space, and newline > all others."""
        assert CHAR_DELAYS["newline"] > CHAR_DELAYS["punctuation"]
        assert CHAR_DELAYS["punctuation"] > CHAR_DELAYS["default"]
        assert CHAR_DELAYS["default"] > CHAR_DELAYS["space"]

    @pytest.mark.asyncio
    async def test_custom_base_delay(self) -> None:
        """Custom base_delay_ms scales all delays proportionally."""
        text = "a."
        custom_ms = 100.0
        custom_s = custom_ms / 1000.0

        with patch("claude_teletype.pacer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await pace_characters(text, base_delay_ms=custom_ms, output_fn=lambda c: None)

        assert mock_sleep.call_args_list[0].args[0] == pytest.approx(
            custom_s * CHAR_DELAYS["default"]
        )
        assert mock_sleep.call_args_list[1].args[0] == pytest.approx(
            custom_s * CHAR_DELAYS["punctuation"]
        )

    @pytest.mark.asyncio
    async def test_empty_string(self) -> None:
        """Empty string produces no output and no sleep calls."""
        collected: list[str] = []

        with patch("claude_teletype.pacer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await pace_characters("", output_fn=collected.append)

        assert collected == []
        assert mock_sleep.call_count == 0

    @pytest.mark.asyncio
    async def test_stdout_fallback(self) -> None:
        """When output_fn is None, writes to sys.stdout."""
        with (
            patch("claude_teletype.pacer.asyncio.sleep", new_callable=AsyncMock),
            patch("claude_teletype.pacer.sys.stdout") as mock_stdout,
        ):
            await pace_characters("ab")

        assert mock_stdout.write.call_count == 2
        mock_stdout.write.assert_any_call("a")
        mock_stdout.write.assert_any_call("b")
        assert mock_stdout.flush.call_count == 2
