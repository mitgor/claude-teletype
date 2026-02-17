"""Tests for the LLM backend abstraction layer."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from claude_teletype.bridge import StreamResult


# --- Task 1: ABC, factory, and Claude CLI backend tests ---


class TestCreateBackendFactory:
    """Tests for create_backend factory function."""

    def test_create_backend_claude_cli(self) -> None:
        """Factory returns ClaudeCliBackend for 'claude-cli'."""
        from claude_teletype.backends import create_backend
        from claude_teletype.backends.claude_cli import ClaudeCliBackend

        backend = create_backend("claude-cli")
        assert isinstance(backend, ClaudeCliBackend)

    def test_create_backend_openai(self) -> None:
        """Factory returns OpenAIBackend for 'openai' (with env var set)."""
        from claude_teletype.backends import create_backend
        from claude_teletype.backends.openai_backend import OpenAIBackend

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            backend = create_backend("openai")
        assert isinstance(backend, OpenAIBackend)

    def test_create_backend_openrouter(self) -> None:
        """Factory returns OpenRouterBackend for 'openrouter' (with env var set)."""
        from claude_teletype.backends import create_backend
        from claude_teletype.backends.openai_backend import OpenRouterBackend

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            backend = create_backend("openrouter")
        assert isinstance(backend, OpenRouterBackend)

    def test_create_backend_unknown(self) -> None:
        """Factory raises BackendError for unknown backend name."""
        from claude_teletype.backends import BackendError, create_backend

        with pytest.raises(BackendError, match="Unknown backend"):
            create_backend("imaginary-backend")


class TestClaudeCliBackendValidation:
    """Tests for ClaudeCliBackend.validate()."""

    def test_claude_cli_validate_missing(self) -> None:
        """validate() raises BackendError when claude is not on PATH."""
        from claude_teletype.backends import BackendError
        from claude_teletype.backends.claude_cli import ClaudeCliBackend

        backend = ClaudeCliBackend()
        with patch("shutil.which", return_value=None):
            with pytest.raises(BackendError, match="Claude Code CLI"):
                backend.validate()

    def test_claude_cli_validate_present(self) -> None:
        """validate() passes when claude binary is found on PATH."""
        from claude_teletype.backends.claude_cli import ClaudeCliBackend

        backend = ClaudeCliBackend()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            backend.validate()  # Should not raise


class TestClaudeCliBackendStream:
    """Tests for ClaudeCliBackend.stream() delegation to bridge.py."""

    @pytest.mark.asyncio
    async def test_claude_cli_stream_delegates(self) -> None:
        """stream() yields same items as mocked stream_claude_response."""
        from claude_teletype.backends.claude_cli import ClaudeCliBackend

        mock_items = ["Hello", ", world!", StreamResult(session_id="new-session")]

        async def mock_stream(*args, **kwargs):
            for item in mock_items:
                yield item

        backend = ClaudeCliBackend()

        with patch(
            "claude_teletype.backends.claude_cli.stream_claude_response",
            side_effect=mock_stream,
        ):
            items = []
            async for item in backend.stream("test prompt"):
                items.append(item)

        assert items[0] == "Hello"
        assert items[1] == ", world!"
        assert isinstance(items[2], StreamResult)

    @pytest.mark.asyncio
    async def test_claude_cli_session_id_updated(self) -> None:
        """After streaming, session_id is updated from StreamResult."""
        from claude_teletype.backends.claude_cli import ClaudeCliBackend

        mock_items = ["Hello", StreamResult(session_id="updated-session-id")]

        async def mock_stream(*args, **kwargs):
            for item in mock_items:
                yield item

        backend = ClaudeCliBackend()
        assert backend.session_id is None

        with patch(
            "claude_teletype.backends.claude_cli.stream_claude_response",
            side_effect=mock_stream,
        ):
            async for _ in backend.stream("test"):
                pass

        assert backend.session_id == "updated-session-id"

    def test_claude_cli_add_to_history_noop(self) -> None:
        """add_to_history() does nothing (no error, no state change)."""
        from claude_teletype.backends.claude_cli import ClaudeCliBackend

        backend = ClaudeCliBackend()
        # Should not raise
        backend.add_to_history("user", "hello")
        backend.add_to_history("assistant", "world")
        # No state change to verify -- it's a no-op
