"""Tests for the Claude Code subprocess bridge module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_teletype.bridge import parse_text_delta, stream_claude_response

# --- Test fixtures: NDJSON lines from 01-RESEARCH.md Code Examples ---

SYSTEM_INIT = json.dumps(
    {
        "type": "system",
        "subtype": "init",
        "session_id": "550e8400-test",
        "model": "claude-sonnet-4-5-20250929",
        "tools": ["Bash", "Read", "Edit"],
        "claude_code_version": "2.1.3",
    }
).encode()

MESSAGE_START = json.dumps(
    {
        "type": "stream_event",
        "session_id": "550e8400-test",
        "event": {
            "type": "message_start",
            "message": {"model": "claude-sonnet-4-5-20250929"},
        },
    }
).encode()

CONTENT_BLOCK_START = json.dumps(
    {
        "type": "stream_event",
        "session_id": "550e8400-test",
        "event": {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
    }
).encode()

TEXT_DELTA_HELLO = json.dumps(
    {
        "type": "stream_event",
        "session_id": "550e8400-test",
        "event": {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello"},
        },
    }
).encode()

TEXT_DELTA_WORLD = json.dumps(
    {
        "type": "stream_event",
        "session_id": "550e8400-test",
        "event": {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": ", world!"},
        },
    }
).encode()

INPUT_JSON_DELTA = json.dumps(
    {
        "type": "stream_event",
        "session_id": "550e8400-test",
        "event": {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"command":'},
        },
    }
).encode()

CONTENT_BLOCK_STOP = json.dumps(
    {
        "type": "stream_event",
        "session_id": "550e8400-test",
        "event": {"type": "content_block_stop", "index": 0},
    }
).encode()

MESSAGE_DELTA = json.dumps(
    {
        "type": "stream_event",
        "session_id": "550e8400-test",
        "event": {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
        },
    }
).encode()

MESSAGE_STOP = json.dumps(
    {
        "type": "stream_event",
        "session_id": "550e8400-test",
        "event": {"type": "message_stop"},
    }
).encode()

ASSISTANT_MESSAGE = json.dumps(
    {
        "type": "assistant",
        "session_id": "550e8400-test",
        "message": {
            "content": [{"type": "text", "text": "Hello, world!"}],
            "stop_reason": "end_turn",
        },
    }
).encode()

RESULT_MESSAGE = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "session_id": "550e8400-test",
        "is_error": False,
        "result": "Hello, world!",
        "total_cost_usd": 0.0234,
    }
).encode()


class TestParseTextDelta:
    """Tests for parse_text_delta helper function."""

    def test_valid_text_delta(self) -> None:
        """text_delta event returns the text content."""
        result = parse_text_delta(TEXT_DELTA_HELLO)
        assert result == "Hello"

    def test_message_start_returns_none(self) -> None:
        """message_start event returns None."""
        assert parse_text_delta(MESSAGE_START) is None

    def test_content_block_start_returns_none(self) -> None:
        """content_block_start event returns None."""
        assert parse_text_delta(CONTENT_BLOCK_START) is None

    def test_input_json_delta_returns_none(self) -> None:
        """content_block_delta with input_json_delta (tool use) returns None."""
        assert parse_text_delta(INPUT_JSON_DELTA) is None

    def test_content_block_stop_returns_none(self) -> None:
        """content_block_stop event returns None."""
        assert parse_text_delta(CONTENT_BLOCK_STOP) is None

    def test_message_stop_returns_none(self) -> None:
        """message_stop event returns None."""
        assert parse_text_delta(MESSAGE_STOP) is None

    def test_result_message_returns_none(self) -> None:
        """result message (non-stream_event type) returns None."""
        assert parse_text_delta(RESULT_MESSAGE) is None

    def test_malformed_json_returns_none(self) -> None:
        """Malformed JSON line returns None."""
        assert parse_text_delta(b"not valid json {{{") is None

    def test_empty_line_returns_none(self) -> None:
        """Empty line returns None."""
        assert parse_text_delta(b"") is None

    def test_whitespace_only_returns_none(self) -> None:
        """Whitespace-only line returns None."""
        assert parse_text_delta(b"   \n") is None

    def test_system_init_returns_none(self) -> None:
        """System init message returns None."""
        assert parse_text_delta(SYSTEM_INIT) is None

    def test_assistant_message_returns_none(self) -> None:
        """Assistant message returns None."""
        assert parse_text_delta(ASSISTANT_MESSAGE) is None

    def test_message_delta_returns_none(self) -> None:
        """message_delta event returns None."""
        assert parse_text_delta(MESSAGE_DELTA) is None

    def test_text_delta_with_empty_text_returns_none(self) -> None:
        """text_delta with empty text string returns None."""
        empty_text = json.dumps(
            {
                "type": "stream_event",
                "session_id": "test",
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": ""},
                },
            }
        ).encode()
        assert parse_text_delta(empty_text) is None


class TestStreamClaudeResponse:
    """Tests for stream_claude_response async generator."""

    @pytest.mark.asyncio
    async def test_yields_text_from_mock_subprocess(self) -> None:
        """Yields correct text chunks from a mock subprocess with NDJSON lines."""
        # Simulate the full NDJSON stream sequence
        ndjson_lines = [
            SYSTEM_INIT + b"\n",
            MESSAGE_START + b"\n",
            CONTENT_BLOCK_START + b"\n",
            TEXT_DELTA_HELLO + b"\n",
            TEXT_DELTA_WORLD + b"\n",
            CONTENT_BLOCK_STOP + b"\n",
            MESSAGE_DELTA + b"\n",
            MESSAGE_STOP + b"\n",
            ASSISTANT_MESSAGE + b"\n",
            RESULT_MESSAGE + b"\n",
            b"",  # EOF
        ]

        # Build a mock process with stdout that returns lines in sequence
        mock_stdout = MagicMock()
        line_iter = iter(ndjson_lines)
        mock_stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.terminate = MagicMock()

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ) as mock_exec:
            chunks: list[str] = []
            async for text in stream_claude_response("test prompt"):
                chunks.append(text)

        assert chunks == ["Hello", ", world!"]

        # Verify subprocess was called with correct args
        mock_exec.assert_called_once_with(
            "claude",
            "-p",
            "test prompt",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--dangerously-skip-permissions",
            "--allowedTools",
            "WebSearch",
            "--allowedTools",
            "WebFetch",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        mock_proc.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_non_text_events(self) -> None:
        """Only text_delta events produce yielded text."""
        ndjson_lines = [
            SYSTEM_INIT + b"\n",
            MESSAGE_START + b"\n",
            CONTENT_BLOCK_START + b"\n",
            INPUT_JSON_DELTA + b"\n",  # tool use -- should be skipped
            TEXT_DELTA_HELLO + b"\n",
            CONTENT_BLOCK_STOP + b"\n",
            MESSAGE_STOP + b"\n",
            RESULT_MESSAGE + b"\n",
            b"",  # EOF
        ]

        mock_stdout = MagicMock()
        line_iter = iter(ndjson_lines)
        mock_stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.terminate = MagicMock()

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ):
            chunks: list[str] = []
            async for text in stream_claude_response("test"):
                chunks.append(text)

        assert chunks == ["Hello"]

    @pytest.mark.asyncio
    async def test_handles_malformed_json_in_stream(self) -> None:
        """Malformed JSON lines in the stream are skipped gracefully."""
        ndjson_lines = [
            b"not valid json\n",
            TEXT_DELTA_HELLO + b"\n",
            b"also {broken\n",
            TEXT_DELTA_WORLD + b"\n",
            b"",  # EOF
        ]

        mock_stdout = MagicMock()
        line_iter = iter(ndjson_lines)
        mock_stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.terminate = MagicMock()

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ):
            chunks: list[str] = []
            async for text in stream_claude_response("test"):
                chunks.append(text)

        assert chunks == ["Hello", ", world!"]

    @pytest.mark.asyncio
    async def test_terminates_process_on_exception(self) -> None:
        """Process is terminated if an exception occurs during streaming."""
        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(side_effect=RuntimeError("test error"))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.terminate = MagicMock()

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ):
            with pytest.raises(RuntimeError, match="test error"):
                async for _ in stream_claude_response("test"):
                    pass

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_awaited_once()
