"""
Slack API Exception Module.

This module defines the custom exception raised when a Slack API request fails.
"""

from __future__ import annotations

from typing import Any


class SlackApiError(Exception):
    """Raised when an API call fails or returns an error response (`ok=False`).

    Attributes:
        error (str): The Slack API error code or failure description.
        raw_response (dict): The complete raw response dictionary, if available.
    """

    def __init__(self, error: str, raw_response: dict[str, Any] | None = None) -> None:
        """Initialize the SlackApiError exception.

        Args:
            error: The error message or error code returned by Slack or CLI.
            raw_response: Optional raw JSON dictionary payload from Slack.
        """
        super().__init__(f"Slack API error: {error}")
        self.error: str = error
        self.raw_response: dict[str, Any] = raw_response or {}
