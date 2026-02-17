"""Tests for the LLM backend abstraction layer."""

import os
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

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


# --- Task 2: OpenAI and OpenRouter backend tests ---


# Helpers for mocking OpenAI streaming responses


@dataclass
class MockDelta:
    """Mock for chunk.choices[0].delta."""

    content: str | None = None
    role: str | None = None


@dataclass
class MockChoice:
    """Mock for chunk.choices[0]."""

    delta: MockDelta
    finish_reason: str | None = None


@dataclass
class MockChunk:
    """Mock for a streaming ChatCompletionChunk."""

    choices: list[MockChoice]


async def mock_stream(chunks: list[MockChunk]):
    """Async iterator yielding mock chunks."""
    for chunk in chunks:
        yield chunk


class TestOpenAIBackendValidation:
    """Tests for OpenAIBackend.validate()."""

    def test_openai_validate_no_key(self) -> None:
        """validate() raises BackendError when api_key is None."""
        from claude_teletype.backends import BackendError
        from claude_teletype.backends.openai_backend import OpenAIBackend

        backend = OpenAIBackend(api_key=None, model="gpt-4o")
        with pytest.raises(BackendError, match="OPENAI_API_KEY"):
            backend.validate()

    def test_openai_validate_with_key(self) -> None:
        """validate() passes when api_key is set."""
        from claude_teletype.backends.openai_backend import OpenAIBackend

        backend = OpenAIBackend(api_key="test-key-123", model="gpt-4o")
        backend.validate()  # Should not raise


class TestOpenAIBackendStream:
    """Tests for OpenAIBackend.stream() behavior."""

    @pytest.mark.asyncio
    async def test_openai_stream_yields_text_and_result(self) -> None:
        """stream() yields str chunks then StreamResult(is_error=False)."""
        from claude_teletype.backends.openai_backend import OpenAIBackend

        chunks = [
            MockChunk(choices=[MockChoice(delta=MockDelta(role="assistant"))]),
            MockChunk(choices=[MockChoice(delta=MockDelta(content="Hello"))]),
            MockChunk(choices=[MockChoice(delta=MockDelta(content=" world"))]),
            MockChunk(choices=[MockChoice(delta=MockDelta(), finish_reason="stop")]),
        ]

        backend = OpenAIBackend(api_key="test-key", model="gpt-4o")
        mock_create = AsyncMock(return_value=mock_stream(chunks))

        with patch.object(backend._client.chat.completions, "create", mock_create):
            items = []
            async for item in backend.stream("Hi"):
                items.append(item)

        assert items[0] == "Hello"
        assert items[1] == " world"
        assert isinstance(items[2], StreamResult)
        assert items[2].is_error is False
        assert items[2].model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_openai_stream_accumulates_history(self) -> None:
        """After streaming, history has user + assistant messages."""
        from claude_teletype.backends.openai_backend import OpenAIBackend

        chunks = [
            MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi there"))]),
        ]

        backend = OpenAIBackend(api_key="test-key", model="gpt-4o")
        mock_create = AsyncMock(return_value=mock_stream(chunks))

        with patch.object(backend._client.chat.completions, "create", mock_create):
            async for _ in backend.stream("Hello"):
                pass

        assert len(backend._history) == 2
        assert backend._history[0] == {"role": "user", "content": "Hello"}
        assert backend._history[1] == {"role": "assistant", "content": "Hi there"}

    @pytest.mark.asyncio
    async def test_openai_stream_auth_error(self) -> None:
        """AuthenticationError yields StreamResult(is_error=True) with 'authentication'."""
        import openai

        from claude_teletype.backends.openai_backend import OpenAIBackend

        backend = OpenAIBackend(api_key="bad-key", model="gpt-4o")

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_response.json.return_value = {"error": {"message": "Invalid API key"}}

        err = openai.AuthenticationError(
            message="Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )
        mock_create = AsyncMock(side_effect=err)

        with patch.object(backend._client.chat.completions, "create", mock_create):
            items = []
            async for item in backend.stream("test"):
                items.append(item)

        assert len(items) == 1
        assert isinstance(items[0], StreamResult)
        assert items[0].is_error is True
        assert "authentication" in items[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_openai_stream_rate_limit_error(self) -> None:
        """RateLimitError yields StreamResult(is_error=True) with 'rate limit'."""
        import openai

        from claude_teletype.backends.openai_backend import OpenAIBackend

        backend = OpenAIBackend(api_key="test-key", model="gpt-4o")

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}

        err = openai.RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body={"error": {"message": "Rate limit exceeded"}},
        )
        mock_create = AsyncMock(side_effect=err)

        with patch.object(backend._client.chat.completions, "create", mock_create):
            items = []
            async for item in backend.stream("test"):
                items.append(item)

        assert len(items) == 1
        assert isinstance(items[0], StreamResult)
        assert items[0].is_error is True
        assert "rate limit" in items[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_openai_stream_connection_error(self) -> None:
        """APIConnectionError yields StreamResult(is_error=True) with 'network'."""
        import openai

        from claude_teletype.backends.openai_backend import OpenAIBackend

        backend = OpenAIBackend(api_key="test-key", model="gpt-4o")

        err = openai.APIConnectionError(request=MagicMock())
        mock_create = AsyncMock(side_effect=err)

        with patch.object(backend._client.chat.completions, "create", mock_create):
            items = []
            async for item in backend.stream("test"):
                items.append(item)

        assert len(items) == 1
        assert isinstance(items[0], StreamResult)
        assert items[0].is_error is True
        assert "network" in items[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_openai_stream_none_content_skipped(self) -> None:
        """Chunks with None delta.content are not yielded as text."""
        from claude_teletype.backends.openai_backend import OpenAIBackend

        chunks = [
            MockChunk(choices=[MockChoice(delta=MockDelta(role="assistant"))]),  # None content
            MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"))]),
            MockChunk(choices=[MockChoice(delta=MockDelta(content=None))]),  # None content
            MockChunk(choices=[MockChoice(delta=MockDelta(), finish_reason="stop")]),  # None content
        ]

        backend = OpenAIBackend(api_key="test-key", model="gpt-4o")
        mock_create = AsyncMock(return_value=mock_stream(chunks))

        with patch.object(backend._client.chat.completions, "create", mock_create):
            text_items = []
            async for item in backend.stream("test"):
                if isinstance(item, str):
                    text_items.append(item)

        assert text_items == ["Hi"]


class TestOpenAIBackendMessages:
    """Tests for OpenAIBackend._build_messages() and system prompt."""

    def test_openai_system_prompt(self) -> None:
        """With system_prompt set, _build_messages() includes system message first."""
        from claude_teletype.backends.openai_backend import OpenAIBackend

        backend = OpenAIBackend(
            api_key="test-key", model="gpt-4o", system_prompt="You are helpful."
        )
        backend.add_to_history("user", "Hello")

        messages = backend._build_messages()
        assert messages[0] == {"role": "system", "content": "You are helpful."}
        assert messages[1] == {"role": "user", "content": "Hello"}

    def test_openai_no_system_prompt(self) -> None:
        """Without system_prompt, _build_messages() has no system entry."""
        from claude_teletype.backends.openai_backend import OpenAIBackend

        backend = OpenAIBackend(api_key="test-key", model="gpt-4o")
        backend.add_to_history("user", "Hello")

        messages = backend._build_messages()
        assert len(messages) == 1
        assert messages[0] == {"role": "user", "content": "Hello"}


class TestOpenRouterBackend:
    """Tests for OpenRouterBackend."""

    def test_openrouter_validate_no_key(self) -> None:
        """validate() raises BackendError mentioning OPENROUTER_API_KEY."""
        from claude_teletype.backends import BackendError
        from claude_teletype.backends.openai_backend import OpenRouterBackend

        backend = OpenRouterBackend(api_key=None, model="openai/gpt-4o")
        with pytest.raises(BackendError, match="OPENROUTER_API_KEY"):
            backend.validate()

    def test_openrouter_base_url(self) -> None:
        """Client base_url contains 'openrouter.ai'."""
        from claude_teletype.backends.openai_backend import OpenRouterBackend

        backend = OpenRouterBackend(api_key="test-key", model="openai/gpt-4o")
        assert "openrouter.ai" in str(backend._client.base_url)
