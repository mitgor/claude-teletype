"""Tests for the error classification module."""

import pytest

from claude_teletype.errors import (
    ERROR_MESSAGES,
    ErrorCategory,
    classify_error,
    is_retryable,
)


class TestClassifyError:
    """Tests for classify_error() function."""

    def test_none_returns_unknown(self) -> None:
        """None input returns UNKNOWN."""
        assert classify_error(None) == ErrorCategory.UNKNOWN

    def test_empty_string_returns_unknown(self) -> None:
        """Empty string returns UNKNOWN."""
        assert classify_error("") == ErrorCategory.UNKNOWN

    def test_rate_limit_substring(self) -> None:
        """Message containing 'rate_limit' returns RATE_LIMIT."""
        assert classify_error("something with rate_limit in it") == ErrorCategory.RATE_LIMIT

    def test_429_returns_rate_limit(self) -> None:
        """Message containing '429' returns RATE_LIMIT."""
        assert classify_error("Error: 429 Too Many Requests") == ErrorCategory.RATE_LIMIT

    def test_overloaded_returns_overloaded(self) -> None:
        """Message containing 'overloaded' returns OVERLOADED."""
        assert classify_error("API is overloaded") == ErrorCategory.OVERLOADED

    def test_529_returns_overloaded(self) -> None:
        """Message containing '529' returns OVERLOADED."""
        assert classify_error("529 overloaded_error") == ErrorCategory.OVERLOADED

    def test_not_authenticated_returns_auth(self) -> None:
        """Message containing 'not authenticated' returns AUTH."""
        assert classify_error("not authenticated") == ErrorCategory.AUTH

    def test_invalid_api_key_returns_auth(self) -> None:
        """Message containing 'API key' returns AUTH."""
        assert classify_error("Invalid API key") == ErrorCategory.AUTH

    def test_context_window_returns_context_exhausted(self) -> None:
        """Message containing 'context window' returns CONTEXT_EXHAUSTED."""
        assert classify_error("context window exceeded") == ErrorCategory.CONTEXT_EXHAUSTED

    def test_no_messages_returned_returns_session_corrupt(self) -> None:
        """Message containing 'No messages returned' returns SESSION_CORRUPT."""
        assert classify_error("No messages returned") == ErrorCategory.SESSION_CORRUPT

    def test_econnrefused_returns_network(self) -> None:
        """Message containing 'ECONNREFUSED' returns NETWORK."""
        assert classify_error("ECONNREFUSED") == ErrorCategory.NETWORK

    def test_fetch_failed_returns_network(self) -> None:
        """Message containing 'fetch failed' returns NETWORK."""
        assert classify_error("fetch failed") == ErrorCategory.NETWORK

    def test_random_error_returns_unknown(self) -> None:
        """Unrecognized error message returns UNKNOWN."""
        assert classify_error("some random error") == ErrorCategory.UNKNOWN

    def test_case_insensitive_rate_limit(self) -> None:
        """Classification is case-insensitive."""
        assert classify_error("RATE_LIMIT") == ErrorCategory.RATE_LIMIT


class TestIsRetryable:
    """Tests for is_retryable() function."""

    def test_rate_limit_is_retryable(self) -> None:
        """RATE_LIMIT is retryable."""
        assert is_retryable(ErrorCategory.RATE_LIMIT) is True

    def test_overloaded_is_retryable(self) -> None:
        """OVERLOADED is retryable."""
        assert is_retryable(ErrorCategory.OVERLOADED) is True

    def test_auth_not_retryable(self) -> None:
        """AUTH is not retryable."""
        assert is_retryable(ErrorCategory.AUTH) is False

    def test_network_not_retryable(self) -> None:
        """NETWORK is not retryable."""
        assert is_retryable(ErrorCategory.NETWORK) is False

    def test_unknown_not_retryable(self) -> None:
        """UNKNOWN is not retryable."""
        assert is_retryable(ErrorCategory.UNKNOWN) is False


class TestErrorMessages:
    """Tests for ERROR_MESSAGES dict."""

    def test_every_category_has_message(self) -> None:
        """Every ErrorCategory value has a corresponding entry in ERROR_MESSAGES."""
        for category in ErrorCategory:
            assert category in ERROR_MESSAGES, f"Missing message for {category}"

    def test_all_messages_are_non_empty_strings(self) -> None:
        """All error messages are non-empty strings."""
        for category, message in ERROR_MESSAGES.items():
            assert isinstance(message, str), f"Message for {category} is not a string"
            assert len(message) > 0, f"Message for {category} is empty"
