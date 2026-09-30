"""
Slack API Client Factory / Provider Module.

This module provides the `APIClientProvider` factory class for resolving and
instantiating an `APIClient` protocol instance.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from dotenv import load_dotenv

from .protocol import APIClient
from .web_client import SlackWebClient
from .cli_client import SlackCliClient

load_dotenv()

logger: logging.Logger = logging.getLogger("APIClient.APIClientProvider")


class APIClientProvider:
    """Factory provider that resolves and instantiates an `APIClient`.

    By default, it provides `SlackWebClient` for high-performance in-process HTTP.
    Alternatively, passing `client_type="cli"` or configuring the
    `SLACK_API_CLIENT_TYPE=cli` environment variable provides `SlackCliClient`.
    """

    @classmethod
    def get_client(
        cls,
        client_type: str | None = None,
        token: str | None = None,
        **kwargs: Any,
    ) -> APIClient:
        """Provide an instance conforming to the `APIClient` protocol.

        Args:
            client_type: "web" (default) or "cli". If omitted, inspects the
                `SLACK_API_CLIENT_TYPE` environment variable (default: "web").
            token: Optional Slack token override.
            **kwargs: Extra parameters passed to the client constructor.

        Returns:
            APIClient: An instantiated client satisfying the `APIClient` protocol.

        Raises:
            ValueError: If an unrecognized `client_type` is specified.
        """
        # Determine client type (explicit arg > environment variable > default 'web')
        resolved_type = (
            client_type
            or os.environ.get("SLACK_API_CLIENT_TYPE", "web")
        ).lower().strip()

        logger.info("Resolving API client of type: '%s'", resolved_type)

        if resolved_type in ("web", "slackwebclient", "direct"):
            client: APIClient = SlackWebClient(token=token, **kwargs)
        elif resolved_type in ("cli", "slackcliclient", "slack_cli"):
            client = SlackCliClient(token=token, **kwargs)
        else:
            raise ValueError(
                f"Unknown client_type '{resolved_type}'. Expected 'web' or 'cli'."
            )

        # Structural typing validation
        assert isinstance(client, APIClient), f"{client.__class__.__name__} must satisfy APIClient Protocol"
        return client
