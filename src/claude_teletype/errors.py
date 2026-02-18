"""Error classification for Claude Code subprocess error messages.

Maps raw error strings from Claude Code CLI NDJSON result messages
to actionable categories with user-friendly messages.
"""

from enum import Enum


class ErrorCategory(str, Enum):
    """Categories for Claude Code error classification."""

    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    AUTH = "auth"
    NETWORK = "network"
    CONTEXT_EXHAUSTED = "context_exhausted"
    SESSION_CORRUPT = "session_corrupt"
    UNKNOWN = "unknown"


# Known error message patterns from Claude Code CLI NDJSON output.
# Each tuple is (pattern_string, ErrorCategory). Matching is case-insensitive
# substring search. Order matters: first match wins.
ERROR_PATTERNS: list[tuple[str, ErrorCategory]] = [
    ("rate_limit", ErrorCategory.RATE_LIMIT),
    ("rate limit", ErrorCategory.RATE_LIMIT),
    ("429", ErrorCategory.RATE_LIMIT),
    ("overloaded", ErrorCategory.OVERLOADED),
    ("529", ErrorCategory.OVERLOADED),
    ("not authenticated", ErrorCategory.AUTH),
    ("authentication", ErrorCategory.AUTH),
    ("api key", ErrorCategory.AUTH),
    ("context window", ErrorCategory.CONTEXT_EXHAUSTED),
    ("context length", ErrorCategory.CONTEXT_EXHAUSTED),
    ("no messages returned", ErrorCategory.SESSION_CORRUPT),
    ("fetch failed", ErrorCategory.NETWORK),
    ("econnrefused", ErrorCategory.NETWORK),
    ("etimedout", ErrorCategory.NETWORK),
    ("network", ErrorCategory.NETWORK),
]

# User-friendly messages for each error category.
ERROR_MESSAGES: dict[ErrorCategory, str] = {
    ErrorCategory.RATE_LIMIT: "Rate limit reached. Retrying...",
    ErrorCategory.OVERLOADED: "Claude is temporarily overloaded. Retrying...",
    ErrorCategory.AUTH: "Authentication error. Run 'claude auth' to re-authenticate.",
    ErrorCategory.NETWORK: "Network error. Check your internet connection.",
    ErrorCategory.CONTEXT_EXHAUSTED: "Context window exhausted. Start a new conversation.",
    ErrorCategory.SESSION_CORRUPT: "Session corrupted. Starting new session.",
    ErrorCategory.UNKNOWN: "An error occurred. Check Claude Code logs for details.",
}


def classify_error(error_message: str | None) -> ErrorCategory:
    """Classify an error message from Claude Code into a category.

    Args:
        error_message: The raw error message string from StreamResult,
            or None if no message was available.

    Returns:
        The matching ErrorCategory, or UNKNOWN if no pattern matches.
    """
    if not error_message:
        return ErrorCategory.UNKNOWN

    lower = error_message.lower()

    for pattern, category in ERROR_PATTERNS:
        if pattern.lower() in lower:
            return category

    # Special case: phrases like "maximum context length" or "max tokens exceeded"
    # but NOT bare "max_tokens" (common OpenAI/OpenRouter parameter name in errors)
    if "max" in lower and "token" in lower and "exceed" in lower:
        return ErrorCategory.CONTEXT_EXHAUSTED

    return ErrorCategory.UNKNOWN


def is_retryable(category: ErrorCategory) -> bool:
    """Check whether an error category is retryable.

    Only transient errors (rate limit, overloaded) are retryable.
    Auth, network, context exhausted, session corrupt, and unknown
    errors require user action or a new session.

    Args:
        category: The error category to check.

    Returns:
        True if the error is retryable, False otherwise.
    """
    return category in {ErrorCategory.RATE_LIMIT, ErrorCategory.OVERLOADED}
