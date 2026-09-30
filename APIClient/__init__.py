"""
APIClient Package — Modular Slack API Client Architecture.

This package provides:
- `APIClient`: Protocol defining the contract for Slack API interactions.
- `SlackWebClient`: In-process HTTPS client implementation using `slack_sdk`.
- `SlackCliClient`: Subprocess client implementation using the `slack api` CLI.
- `APIClientProvider`: Factory class providing `APIClient` instances.
- `SlackApiError`: Custom exception raised on Slack API failures.
"""

from .exceptions import SlackApiError
from .protocol import APIClient
from .web_client import SlackWebClient
from .cli_client import SlackCliClient
from .provider import APIClientProvider

__all__ = [
    "APIClient",
    "SlackWebClient",
    "SlackCliClient",
    "APIClientProvider",
    "SlackApiError",
]
