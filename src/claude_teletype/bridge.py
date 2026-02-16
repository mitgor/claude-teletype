"""Claude Code subprocess bridge for streaming NDJSON responses.

Spawns the Claude Code CLI, reads its NDJSON stream output,
and yields text chunks from text_delta events. Supports multi-turn
sessions via --resume flag and returns session metadata as StreamResult.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class StreamResult:
    """Session metadata yielded as the final item from stream_claude_response.

    Contains session_id for multi-turn resume, error status, cost,
    model info, turn count, and usage stats for context percentage calculation.
    """

    session_id: str | None = None
    is_error: bool = False
    error_message: str | None = None
    cost_usd: float | None = None
    model: str | None = None
    num_turns: int | None = None
    usage: dict | None = None
    model_usage: dict | None = None


def parse_text_delta(line: bytes) -> str | None:
    """Parse a raw NDJSON line and extract text_delta text if present.

    Args:
        line: Raw bytes from the subprocess stdout.

    Returns:
        The text string from a text_delta event, or None for all other events.
    """
    if not line or not line.strip():
        return None

    try:
        msg = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if msg.get("type") != "stream_event":
        return None

    event = msg.get("event", {})
    if event.get("type") != "content_block_delta":
        return None

    delta = event.get("delta", {})
    if delta.get("type") != "text_delta":
        return None

    text = delta.get("text", "")
    return text if text else None


def parse_session_id(line: bytes) -> str | None:
    """Extract session_id from the system init NDJSON line.

    Args:
        line: Raw bytes from the subprocess stdout.

    Returns:
        The session_id string from a system/init message, or None.
    """
    if not line or not line.strip():
        return None
    try:
        msg = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if msg.get("type") == "system" and msg.get("subtype") == "init":
        return msg.get("session_id")
    return None


def parse_result(line: bytes) -> dict | None:
    """Extract result message fields including usage stats.

    Args:
        line: Raw bytes from the subprocess stdout.

    Returns:
        Dict with is_error, result, cost_usd, num_turns, session_id,
        usage, model_usage fields, or None for non-result messages.
    """
    if not line or not line.strip():
        return None
    try:
        msg = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if msg.get("type") != "result":
        return None
    return {
        "is_error": msg.get("is_error", False),
        "result": msg.get("result", ""),
        "cost_usd": msg.get("total_cost_usd"),
        "num_turns": msg.get("num_turns"),
        "session_id": msg.get("session_id"),
        "usage": msg.get("usage"),
        "model_usage": msg.get("modelUsage"),
    }


def calc_context_pct(model_usage: dict | None) -> str:
    """Calculate context usage percentage from modelUsage data.

    Args:
        model_usage: The modelUsage dict from a result NDJSON message,
            keyed by model name with token counts and contextWindow.

    Returns:
        Formatted percentage string like "20%", or "--" if unavailable.
    """
    if not model_usage:
        return "--"
    for _model_name, usage in model_usage.items():
        context_window = usage.get("contextWindow", 0)
        if context_window == 0:
            return "--"
        total_tokens = (
            usage.get("inputTokens", 0)
            + usage.get("outputTokens", 0)
            + usage.get("cacheReadInputTokens", 0)
            + usage.get("cacheCreationInputTokens", 0)
        )
        pct = (total_tokens / context_window) * 100
        return f"{pct:.0f}%"
    return "--"


def extract_model_name(model_usage: dict | None) -> str | None:
    """Extract model name from modelUsage dict keys.

    Args:
        model_usage: The modelUsage dict from a result NDJSON message.

    Returns:
        The first model name string, or None if unavailable.
    """
    if not model_usage:
        return None
    for model_name in model_usage:
        return model_name
    return None


async def stream_claude_response(
    prompt: str,
    session_id: str | None = None,
    proc_holder: list | None = None,
) -> AsyncIterator[str | StreamResult]:
    """Spawn Claude Code and yield text chunks as they stream in.

    Uses one-shot mode (-p) with stream-json output format to get
    token-level streaming via NDJSON. Filters for text_delta events
    and yields the text content. Yields a StreamResult as the final
    item with session metadata parsed from system/init and result messages.

    Args:
        prompt: The prompt to send to Claude Code.
        session_id: Optional session ID for multi-turn resume via --resume flag.
        proc_holder: Optional mutable list; populated with subprocess reference
            after spawn for external lifecycle management (e.g., cancel from TUI).

    Yields:
        Text strings from text_delta events, followed by a single StreamResult.
    """
    args = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--dangerously-skip-permissions",
        "--allowedTools",
        "WebSearch",
        "--allowedTools",
        "WebFetch",
    ]
    if session_id is not None:
        args.extend(["--resume", session_id])

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    if proc_holder is not None:
        proc_holder.clear()
        proc_holder.append(proc)

    assert proc.stdout is not None

    captured_session_id: str | None = None
    captured_result: dict | None = None

    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break  # EOF

            # Parse session_id from system/init message
            sid = parse_session_id(line)
            if sid is not None:
                captured_session_id = sid

            # Parse result message for usage stats
            result_data = parse_result(line)
            if result_data is not None:
                captured_result = result_data

            # Yield text chunks
            text = parse_text_delta(line)
            if text is not None:
                yield text

        await proc.wait()

        # Build and yield StreamResult from captured data
        sr = StreamResult(session_id=captured_session_id)
        if captured_result is not None:
            sr.is_error = captured_result.get("is_error", False)
            if sr.is_error:
                sr.error_message = captured_result.get("result")
            sr.cost_usd = captured_result.get("cost_usd")
            sr.num_turns = captured_result.get("num_turns")
            sr.usage = captured_result.get("usage")
            sr.model_usage = captured_result.get("model_usage")
            sr.model = extract_model_name(captured_result.get("model_usage"))
            # Prefer session_id from result if not captured from init
            if sr.session_id is None:
                sr.session_id = captured_result.get("session_id")
        yield sr

    except BaseException:
        proc.terminate()
        await proc.wait()
        raise
