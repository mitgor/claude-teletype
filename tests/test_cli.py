"""Tests for _chat_async function in the --no-tui code path."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_teletype.bridge import StreamResult

# Reuse NDJSON fixture constants from test_bridge.py
from tests.test_bridge import (
    RESULT_MESSAGE_ERROR,
    RESULT_MESSAGE_FULL,
    SYSTEM_INIT,
    TEXT_DELTA_HELLO,
)

from claude_teletype.cli import _chat_async


def _make_mock_stream(ndjson_lines: list[bytes]):
    """Build a mock subprocess that yields the given NDJSON lines.

    Returns a mock_proc suitable for patching create_subprocess_exec.
    """
    mock_stdout = MagicMock()
    line_iter = iter(ndjson_lines)
    mock_stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

    mock_proc = MagicMock()
    mock_proc.stdout = mock_stdout
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.terminate = MagicMock()
    return mock_proc


class TestChatAsyncStreamResult:
    """Tests for _chat_async handling of StreamResult from stream_claude_response."""

    @pytest.mark.asyncio
    async def test_chat_async_streams_text_and_handles_stream_result(
        self, tmp_path
    ) -> None:
        """_chat_async completes without crash when StreamResult is the final yield.

        Verifies: no crash, pace_characters called with "Hello" (not StreamResult).
        """
        mock_proc = _make_mock_stream([
            SYSTEM_INIT + b"\n",
            TEXT_DELTA_HELLO + b"\n",
            RESULT_MESSAGE_FULL + b"\n",
            b"",  # EOF
        ])

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
            "claude_teletype.cli.pace_characters",
            new_callable=AsyncMock,
        ) as mock_pace, patch(
            "claude_teletype.cli.console",
        ) as mock_console, patch(
            "claude_teletype.transcript.make_transcript_output",
            return_value=(MagicMock(), MagicMock()),
        ):
            # Set up console.status context manager
            mock_console.status.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_console.status.return_value.__exit__ = MagicMock(
                return_value=False
            )

            await _chat_async(
                "test prompt",
                base_delay_ms=0,
                no_audio=True,
                transcript_dir=str(tmp_path),
            )

        # pace_characters should have been called with "Hello", not StreamResult
        assert mock_pace.call_count >= 1
        for call in mock_pace.call_args_list:
            first_arg = call[0][0]
            assert isinstance(first_arg, str), (
                f"pace_characters received {type(first_arg).__name__}, expected str"
            )

    @pytest.mark.asyncio
    async def test_chat_async_displays_error_stream_result(
        self, tmp_path
    ) -> None:
        """_chat_async prints error message when StreamResult has is_error=True.

        Verifies: console.print called with error message, no call to pace_characters.
        """
        mock_proc = _make_mock_stream([
            RESULT_MESSAGE_ERROR + b"\n",
            b"",  # EOF
        ])

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
            "claude_teletype.cli.pace_characters",
            new_callable=AsyncMock,
        ) as mock_pace, patch(
            "claude_teletype.cli.console",
        ) as mock_console, patch(
            "claude_teletype.transcript.make_transcript_output",
            return_value=(MagicMock(), MagicMock()),
        ):
            mock_console.status.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_console.status.return_value.__exit__ = MagicMock(
                return_value=False
            )

            await _chat_async(
                "test prompt",
                base_delay_ms=0,
                no_audio=True,
                transcript_dir=str(tmp_path),
            )

        # pace_characters should NOT have been called (only error StreamResult)
        mock_pace.assert_not_called()

        # console.print should have been called with the error message
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        error_printed = any("Something went wrong" in c for c in print_calls)
        assert error_printed, (
            f"Expected error message in console.print calls: {print_calls}"
        )

    @pytest.mark.asyncio
    async def test_chat_async_handles_empty_response(
        self, tmp_path
    ) -> None:
        """_chat_async shows 'No response received' when only a success StreamResult is yielded.

        Verifies: no crash, "No response received" message shown.
        """
        # Only a success StreamResult, no text chunks
        mock_proc = _make_mock_stream([
            SYSTEM_INIT + b"\n",
            RESULT_MESSAGE_FULL + b"\n",
            b"",  # EOF
        ])

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
            "claude_teletype.cli.pace_characters",
            new_callable=AsyncMock,
        ) as mock_pace, patch(
            "claude_teletype.cli.console",
        ) as mock_console, patch(
            "claude_teletype.transcript.make_transcript_output",
            return_value=(MagicMock(), MagicMock()),
        ):
            mock_console.status.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_console.status.return_value.__exit__ = MagicMock(
                return_value=False
            )

            await _chat_async(
                "test prompt",
                base_delay_ms=0,
                no_audio=True,
                transcript_dir=str(tmp_path),
            )

        # No text was streamed, so pace_characters should not be called
        mock_pace.assert_not_called()

        # "No response received" message should be shown
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        no_response_shown = any("No response received" in c for c in print_calls)
        assert no_response_shown, (
            f"Expected 'No response received' in console.print calls: {print_calls}"
        )
