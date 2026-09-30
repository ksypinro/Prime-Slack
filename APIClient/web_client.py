"""
Direct Slack Web API Client Implementation.

This module implements the `APIClient` protocol using `slack_sdk.WebClient`
over persistent HTTPS connections with connection pooling.
"""

from __future__ import annotations

import os
from typing import Any
from dotenv import load_dotenv

from .exceptions import SlackApiError

load_dotenv()


class SlackWebClient:
    """Sends HTTP requests directly to the Slack Web API using `slack_sdk.WebClient`.

    This client maintains an in-process HTTP session and executes direct HTTPS
    POST/GET requests to `https://slack.com/api/{method}` with persistent HTTP
    keep-alive connection pooling.
    """

    def __init__(self, token: str | None = None) -> None:
        """Initialize the direct Web API client.

        Args:
            token: Slack Bot token (`xoxb-...`) or User token (`xoxp-...`).
                   Defaults to the `SLACK_BOT_TOKEN` environment variable.
        """
        self.token: str = token or os.environ.get("SLACK_BOT_TOKEN", "")
        if not self.token:
            raise ValueError("SLACK_BOT_TOKEN must be provided or set in environment.")

        from slack_sdk import WebClient
        self._client: WebClient = WebClient(token=self.token)

    def call(self, method: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke an arbitrary Slack Web API method directly via HTTP.

        Args:
            method: The Slack API method name (e.g. 'auth.test', 'chat.postMessage').
            **kwargs: Parameters passed to the method as keyword arguments.

        Returns:
            dict: Parsed JSON response payload from Slack.

        Raises:
            SlackApiError: If the API returns ok=False or request fails.
        """
        from slack_sdk.errors import SlackApiError as SdkApiError

        try:
            response = self._client.api_call(api_method=method, json=kwargs if kwargs else None)
            data: dict[str, Any] = response.data  # type: ignore[assignment]
            if not data.get("ok"):
                raise SlackApiError(error=data.get("error", "unknown_error"), raw_response=data)
            return data
        except SdkApiError as err:
            error_code = err.response.get("error", str(err))
            raise SlackApiError(error=error_code, raw_response=err.response.data) from err

    def post_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Post a message via `chat.postMessage`."""
        params: dict[str, Any] = {"channel": channel, "text": text, **kwargs}
        if thread_ts:
            params["thread_ts"] = thread_ts
        return self.call("chat.postMessage", **params)

    def add_reaction(
        self,
        channel: str,
        timestamp: str,
        name: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add an emoji reaction via `reactions.add`."""
        return self.call("reactions.add", channel=channel, timestamp=timestamp, name=name, **kwargs)

    def get_conversation_replies(
        self,
        channel: str,
        ts: str,
        limit: int = 50,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Fetch conversation thread messages via `conversations.replies`."""
        return self.call("conversations.replies", channel=channel, ts=ts, limit=limit, **kwargs)

    def auth_test(self, **kwargs: Any) -> dict[str, Any]:
        """Check authentication status via `auth.test`."""
        return self.call("auth.test", **kwargs)
