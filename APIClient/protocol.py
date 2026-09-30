"""
Slack API Protocol Definition.

This module defines the `APIClient` protocol using PEP 544 structural subtyping.
Any conforming Slack API client must implement this interface.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class APIClient(Protocol):
    """Protocol defining the interface for Slack API clients.

    Any conforming implementation (such as `SlackWebClient` or `SlackCliClient`)
    can be used interchangeably by the application layer without coupling to
    specific transport mechanisms.
    """

    def call(self, method: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke any Slack Web API method dynamically.

        Args:
            method: The API method name (e.g. 'chat.postMessage', 'auth.test').
            **kwargs: Parameters passed to the method as keyword arguments.

        Returns:
            dict: Parsed JSON response payload from Slack.

        Raises:
            SlackApiError: If the API returns ok=False or request fails.
        """
        ...

    def post_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Post a message to a channel or thread (`chat.postMessage`).

        Args:
            channel: Slack channel ID.
            text: Message body text (supports mrkdwn).
            thread_ts: Optional parent thread timestamp to nest the reply.
            **kwargs: Extra parameters (e.g. blocks, attachments).

        Returns:
            dict: Slack response dictionary containing ts, channel, etc.
        """
        ...

    def add_reaction(
        self,
        channel: str,
        timestamp: str,
        name: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add an emoji reaction to a message (`reactions.add`).

        Args:
            channel: Slack channel ID containing the message.
            timestamp: Message timestamp to react to.
            name: Emoji name without colons (e.g. 'eyes', 'white_check_mark').
            **kwargs: Extra parameters.

        Returns:
            dict: Slack response dictionary.
        """
        ...

    def get_conversation_replies(
        self,
        channel: str,
        ts: str,
        limit: int = 50,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Retrieve replies in a conversation thread (`conversations.replies`).

        Args:
            channel: Slack channel ID.
            ts: Parent thread timestamp.
            limit: Maximum number of messages to retrieve (default 50).
            **kwargs: Extra parameters.

        Returns:
            dict: Slack response dictionary containing messages list.
        """
        ...

    def auth_test(self, **kwargs: Any) -> dict[str, Any]:
        """Verify bot authentication and retrieve identity (`auth.test`).

        Returns:
            dict: Slack response dictionary containing user, bot_id, team, etc.
        """
        ...
