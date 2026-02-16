"""Tests for the Claude Code subprocess bridge module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_teletype.bridge import (
    StreamResult,
    calc_context_pct,
    extract_model_name,
    parse_result,
    parse_session_id,
    parse_text_delta,
    stream_claude_response,
)

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

RESULT_MESSAGE_FULL = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "session_id": "550e8400-test",
        "is_error": False,
        "result": "Hello, world!",
        "total_cost_usd": 0.0234,
        "num_turns": 3,
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "modelUsage": {
            "claude-sonnet-4-5-20250929": {
                "inputTokens": 9,
                "outputTokens": 143,
                "cacheReadInputTokens": 39900,
                "cacheCreationInputTokens": 439,
                "contextWindow": 200000,
                "maxOutputTokens": 64000,
                "costUSD": 0.0157882,
            }
        },
    }
).encode()

RESULT_MESSAGE_ERROR = json.dumps(
    {
        "type": "result",
        "subtype": "error",
        "session_id": "550e8400-test",
        "is_error": True,
        "result": "Something went wrong",
        "total_cost_usd": 0.001,
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
            async for item in stream_claude_response("test prompt"):
                if isinstance(item, str):
                    chunks.append(item)

        assert chunks == ["Hello", ", world!"]

        # Verify subprocess was called with correct args (positional via *args)
        call_args = mock_exec.call_args[0]
        assert call_args == (
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
            async for item in stream_claude_response("test"):
                if isinstance(item, str):
                    chunks.append(item)

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
            async for item in stream_claude_response("test"):
                if isinstance(item, str):
                    chunks.append(item)

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


class TestParseSessionId:
    """Tests for parse_session_id helper function."""

    def test_extracts_session_id_from_system_init(self) -> None:
        """system/init NDJSON line returns session_id string."""
        result = parse_session_id(SYSTEM_INIT)
        assert result == "550e8400-test"

    def test_non_init_message_returns_none(self) -> None:
        """Non-system messages return None."""
        assert parse_session_id(MESSAGE_START) is None

    def test_result_message_returns_none(self) -> None:
        """Result messages return None."""
        assert parse_session_id(RESULT_MESSAGE) is None

    def test_system_non_init_subtype_returns_none(self) -> None:
        """System message with non-init subtype returns None."""
        msg = json.dumps(
            {"type": "system", "subtype": "other", "session_id": "abc123"}
        ).encode()
        assert parse_session_id(msg) is None

    def test_malformed_json_returns_none(self) -> None:
        """Malformed JSON returns None."""
        assert parse_session_id(b"not valid json {{{") is None

    def test_empty_line_returns_none(self) -> None:
        """Empty bytes return None."""
        assert parse_session_id(b"") is None

    def test_whitespace_only_returns_none(self) -> None:
        """Whitespace-only bytes return None."""
        assert parse_session_id(b"   \n") is None


class TestParseResult:
    """Tests for parse_result helper function."""

    def test_extracts_fields_from_result_message(self) -> None:
        """Result NDJSON line returns dict with expected fields."""
        result = parse_result(RESULT_MESSAGE_FULL)
        assert result is not None
        assert result["is_error"] is False
        assert result["result"] == "Hello, world!"
        assert result["cost_usd"] == 0.0234
        assert result["num_turns"] == 3
        assert result["session_id"] == "550e8400-test"
        assert result["usage"] == {"input_tokens": 100, "output_tokens": 50}
        assert "claude-sonnet-4-5-20250929" in result["model_usage"]

    def test_extracts_error_result(self) -> None:
        """Error result message returns is_error=True."""
        result = parse_result(RESULT_MESSAGE_ERROR)
        assert result is not None
        assert result["is_error"] is True
        assert result["result"] == "Something went wrong"

    def test_non_result_message_returns_none(self) -> None:
        """Non-result messages return None."""
        assert parse_result(MESSAGE_START) is None

    def test_system_init_returns_none(self) -> None:
        """System/init messages return None."""
        assert parse_result(SYSTEM_INIT) is None

    def test_malformed_json_returns_none(self) -> None:
        """Malformed JSON returns None."""
        assert parse_result(b"not valid json {{{") is None

    def test_empty_line_returns_none(self) -> None:
        """Empty bytes return None."""
        assert parse_result(b"") is None

    def test_minimal_result_has_defaults(self) -> None:
        """Result message with minimal fields uses defaults."""
        minimal = json.dumps({"type": "result"}).encode()
        result = parse_result(minimal)
        assert result is not None
        assert result["is_error"] is False
        assert result["result"] == ""
        assert result["cost_usd"] is None
        assert result["num_turns"] is None
        assert result["session_id"] is None
        assert result["usage"] is None
        assert result["model_usage"] is None


class TestCalcContextPct:
    """Tests for calc_context_pct helper function."""

    def test_calculates_percentage_correctly(self) -> None:
        """Computes correct percentage from modelUsage data."""
        model_usage = {
            "claude-sonnet-4-5-20250929": {
                "inputTokens": 9,
                "outputTokens": 143,
                "cacheReadInputTokens": 39900,
                "cacheCreationInputTokens": 439,
                "contextWindow": 200000,
            }
        }
        result = calc_context_pct(model_usage)
        # (9 + 143 + 39900 + 439) / 200000 * 100 = 20.2455%
        assert result == "20%"

    def test_none_returns_dash(self) -> None:
        """None input returns '--'."""
        assert calc_context_pct(None) == "--"

    def test_empty_dict_returns_dash(self) -> None:
        """Empty dict returns '--'."""
        assert calc_context_pct({}) == "--"

    def test_zero_context_window_returns_dash(self) -> None:
        """contextWindow of 0 returns '--'."""
        model_usage = {
            "some-model": {
                "inputTokens": 100,
                "outputTokens": 50,
                "cacheReadInputTokens": 0,
                "cacheCreationInputTokens": 0,
                "contextWindow": 0,
            }
        }
        assert calc_context_pct(model_usage) == "--"

    def test_small_usage_rounds_to_zero(self) -> None:
        """Very small token usage rounds to 0%."""
        model_usage = {
            "some-model": {
                "inputTokens": 1,
                "outputTokens": 0,
                "cacheReadInputTokens": 0,
                "cacheCreationInputTokens": 0,
                "contextWindow": 200000,
            }
        }
        assert calc_context_pct(model_usage) == "0%"


class TestExtractModelName:
    """Tests for extract_model_name helper function."""

    def test_returns_first_model_key(self) -> None:
        """Returns the model name from modelUsage dict."""
        model_usage = {"claude-sonnet-4-5-20250929": {"inputTokens": 9}}
        assert extract_model_name(model_usage) == "claude-sonnet-4-5-20250929"

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        assert extract_model_name(None) is None

    def test_empty_dict_returns_none(self) -> None:
        """Empty dict returns None."""
        assert extract_model_name({}) is None


class TestStreamClaudeResponseMultiTurn:
    """Tests for stream_claude_response with session_id, proc_holder, and StreamResult."""

    @pytest.mark.asyncio
    async def test_no_session_id_omits_resume_flag(self) -> None:
        """When session_id is None, --resume is NOT in subprocess args."""
        ndjson_lines = [
            TEXT_DELTA_HELLO + b"\n",
            RESULT_MESSAGE + b"\n",
            b"",
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
        ) as mock_exec:
            items: list[str | StreamResult] = []
            async for item in stream_claude_response("test prompt"):
                items.append(item)

        # Verify --resume is NOT in the call args
        call_args = mock_exec.call_args[0]
        assert "--resume" not in call_args

    @pytest.mark.asyncio
    async def test_session_id_adds_resume_flag(self) -> None:
        """When session_id is provided, --resume session_id is in subprocess args."""
        ndjson_lines = [
            SYSTEM_INIT + b"\n",
            TEXT_DELTA_HELLO + b"\n",
            RESULT_MESSAGE + b"\n",
            b"",
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
        ) as mock_exec:
            items: list[str | StreamResult] = []
            async for item in stream_claude_response(
                "test prompt", session_id="abc-123"
            ):
                items.append(item)

        call_args = mock_exec.call_args[0]
        assert "--resume" in call_args
        resume_idx = call_args.index("--resume")
        assert call_args[resume_idx + 1] == "abc-123"

    @pytest.mark.asyncio
    async def test_proc_holder_populated_after_spawn(self) -> None:
        """When proc_holder is provided, it is populated with the subprocess."""
        ndjson_lines = [
            TEXT_DELTA_HELLO + b"\n",
            RESULT_MESSAGE + b"\n",
            b"",
        ]
        mock_stdout = MagicMock()
        line_iter = iter(ndjson_lines)
        mock_stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.terminate = MagicMock()

        proc_holder: list = []

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ):
            async for _ in stream_claude_response(
                "test", proc_holder=proc_holder
            ):
                pass

        assert len(proc_holder) == 1
        assert proc_holder[0] is mock_proc

    @pytest.mark.asyncio
    async def test_yields_stream_result_as_final_item(self) -> None:
        """StreamResult is yielded as the final item after all text chunks."""
        ndjson_lines = [
            SYSTEM_INIT + b"\n",
            TEXT_DELTA_HELLO + b"\n",
            TEXT_DELTA_WORLD + b"\n",
            RESULT_MESSAGE_FULL + b"\n",
            b"",
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
            items: list[str | StreamResult] = []
            async for item in stream_claude_response("test"):
                items.append(item)

        # Text chunks first, StreamResult last
        assert items[0] == "Hello"
        assert items[1] == ", world!"
        assert isinstance(items[2], StreamResult)

        sr = items[2]
        assert sr.session_id == "550e8400-test"
        assert sr.is_error is False
        assert sr.cost_usd == 0.0234
        assert sr.num_turns == 3
        assert sr.model == "claude-sonnet-4-5-20250929"
        assert sr.model_usage is not None

    @pytest.mark.asyncio
    async def test_stream_result_with_no_result_message(self) -> None:
        """StreamResult is yielded even if no result NDJSON message was received."""
        ndjson_lines = [
            SYSTEM_INIT + b"\n",
            TEXT_DELTA_HELLO + b"\n",
            b"",
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
            items: list[str | StreamResult] = []
            async for item in stream_claude_response("test"):
                items.append(item)

        assert items[0] == "Hello"
        assert isinstance(items[1], StreamResult)
        sr = items[1]
        assert sr.session_id == "550e8400-test"  # From system/init
        assert sr.is_error is False
        assert sr.cost_usd is None
        assert sr.model is None

    @pytest.mark.asyncio
    async def test_backward_compatible_with_existing_tests(self) -> None:
        """Calling with no new params still yields text chunks (and StreamResult)."""
        ndjson_lines = [
            TEXT_DELTA_HELLO + b"\n",
            b"",
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
            text_items: list[str] = []
            async for item in stream_claude_response("test"):
                if isinstance(item, str):
                    text_items.append(item)

        assert text_items == ["Hello"]


class TestStreamClaudeResponseTimeout:
    """Tests for bridge readline timeout behavior."""

    @pytest.mark.asyncio
    async def test_stream_claude_response_yields_error_on_readline_timeout(
        self,
    ) -> None:
        """When readline times out, an error StreamResult is yielded."""
        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError)

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.returncode = None

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ):
            items: list[str | StreamResult] = []
            async for item in stream_claude_response("test prompt"):
                items.append(item)

        # Should yield an error StreamResult
        assert len(items) == 1
        sr = items[0]
        assert isinstance(sr, StreamResult)
        assert sr.is_error is True
        assert "timed out" in sr.error_message

    @pytest.mark.asyncio
    async def test_stream_claude_response_kills_subprocess_on_timeout(
        self,
    ) -> None:
        """On readline timeout, proc.terminate() is called, then proc.kill() if still alive (ERR-04)."""
        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError)

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        # Simulate process not exiting after terminate (first wait times out),
        # then exiting after kill (second wait succeeds)
        mock_proc.wait = AsyncMock(
            side_effect=[asyncio.TimeoutError, 0]
        )
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.returncode = None

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ):
            items: list[str | StreamResult] = []
            async for item in stream_claude_response("test prompt"):
                items.append(item)

        # Verify kill-with-timeout pattern: terminate called, then kill
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_claude_response_uses_shorter_timeout_after_result(
        self,
    ) -> None:
        """After result message, readline uses POST_RESULT_TIMEOUT_SECONDS (30s)."""
        from claude_teletype.bridge import POST_RESULT_TIMEOUT_SECONDS

        ndjson_lines = [
            SYSTEM_INIT + b"\n",
            TEXT_DELTA_HELLO + b"\n",
            RESULT_MESSAGE_FULL + b"\n",
        ]
        call_count = 0

        async def readline_side_effect():
            nonlocal call_count
            if call_count < len(ndjson_lines):
                result = ndjson_lines[call_count]
                call_count += 1
                return result
            # After result, simulate hang (timeout)
            raise asyncio.TimeoutError

        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(side_effect=readline_side_effect)

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.returncode = None

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
            "claude_teletype.bridge.asyncio.wait_for",
            wraps=asyncio.wait_for,
        ) as mock_wait_for:
            items: list[str | StreamResult] = []
            async for item in stream_claude_response("test prompt"):
                items.append(item)

        # Verify wait_for was called with shorter timeout after result.
        # The wait_for calls include: 3 readline calls (INIT, HELLO, RESULT)
        # with READ_TIMEOUT, then 1 readline call with POST_RESULT_TIMEOUT,
        # then 1 proc.wait call with 5.0 in the cleanup handler.
        # Filter for the POST_RESULT_TIMEOUT call (4th readline call).
        timeout_values = [
            call.kwargs.get("timeout") for call in mock_wait_for.call_args_list
        ]
        assert POST_RESULT_TIMEOUT_SECONDS in timeout_values, (
            f"Expected {POST_RESULT_TIMEOUT_SECONDS} in timeout values: {timeout_values}"
        )
