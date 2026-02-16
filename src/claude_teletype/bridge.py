"""Claude Code subprocess bridge for streaming NDJSON responses.

Spawns the Claude Code CLI, reads its NDJSON stream output,
and yields text chunks from text_delta events.
"""

import asyncio
import json
from collections.abc import AsyncIterator


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


async def stream_claude_response(prompt: str) -> AsyncIterator[str]:
    """Spawn Claude Code and yield text chunks as they stream in.

    Uses one-shot mode (-p) with stream-json output format to get
    token-level streaming via NDJSON. Filters for text_delta events
    and yields the text content.

    Args:
        prompt: The prompt to send to Claude Code.

    Yields:
        Text strings from text_delta events.
    """
    proc = await asyncio.create_subprocess_exec(
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
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    assert proc.stdout is not None

    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break  # EOF

            text = parse_text_delta(line)
            if text is not None:
                yield text

        await proc.wait()
    except BaseException:
        proc.terminate()
        await proc.wait()
        raise
