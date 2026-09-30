"""
Slack CLI API Client Implementation.

This module implements the `APIClient` protocol by delegating requests to the
official `slack api` command via subprocess execution.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any
from dotenv import load_dotenv

from .exceptions import SlackApiError

load_dotenv()

logger: logging.Logger = logging.getLogger("APIClient.SlackCliClient")


class SlackCliClient:
    """Sends requests to the Slack API by executing the `slack api` CLI command.

    This client locates the Slack CLI binary on the host system and executes:
        `slack api <method> --json '<payload>' --token <token>`
    """

    def __init__(self, token: str | None = None, cli_path: str | None = None) -> None:
        """Initialize the CLI API client.

        Args:
            token: Slack Bot token. Defaults to `SLACK_BOT_TOKEN`.
            cli_path: Optional explicit path to the `slack` binary.
        """
        self.token: str = token or os.environ.get("SLACK_BOT_TOKEN", "")
        self.cli_path: str = cli_path or self._resolve_cli_path()

    @staticmethod
    def _resolve_cli_path() -> str:
        """Locate the Slack CLI binary across known install locations."""
        path_from_shutil = shutil.which("slack")
        if path_from_shutil:
            return path_from_shutil

        candidate_paths = [
            os.path.expanduser("~/.slack/bin/slack"),
            os.path.expanduser("~/.local/bin/slack"),
            "/usr/local/bin/slack",
            "/opt/homebrew/bin/slack",
        ]
        for candidate in candidate_paths:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        raise FileNotFoundError(
            "Slack CLI executable ('slack') not found. Please install it with:\n"
            "  curl -fsSL https://downloads.slack-edge.com/slack-cli/install.sh | bash"
        )

    def call(self, method: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke an arbitrary Slack Web API method via the `slack api` CLI command.

        Args:
            method: The Slack API method name (e.g. 'auth.test', 'chat.postMessage').
            **kwargs: Parameters passed to the method as keyword arguments.

        Returns:
            dict: Parsed JSON response payload from Slack.

        Raises:
            SlackApiError: If the CLI command fails or returns an error.
        """
        cmd: list[str] = [self.cli_path, "api", method]

        if self.token:
            cmd.extend(["--token", self.token])

        if kwargs:
            cmd.extend(["--json", json.dumps(kwargs)])

        logger.debug("Executing CLI command: %s", " ".join(cmd))

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        stdout_clean = proc.stdout.strip()
        stderr_clean = proc.stderr.strip()

        if proc.returncode != 0:
            error_msg = stderr_clean or stdout_clean or f"CLI exited with code {proc.returncode}"
            raise SlackApiError(error=error_msg)

        try:
            data: dict[str, Any] = json.loads(stdout_clean)
        except json.JSONDecodeError as json_err:
            raise SlackApiError(
                error=f"Failed to parse JSON from CLI stdout: {stdout_clean}",
                raw_response={"stdout": stdout_clean, "stderr": stderr_clean},
            ) from json_err

        if not data.get("ok"):
            raise SlackApiError(error=data.get("error", "cli_api_error"), raw_response=data)

        return data

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
