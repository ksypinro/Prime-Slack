"""
API Client Module — Protocol Abstraction & Factory Pattern for Slack API.

This module establishes a decoupled architecture for executing Slack API requests
using Python's Protocol (PEP 544 structural subtyping) and the Factory Pattern:

1. **Protocol (`APIClient`)**:
   Defines the contract that any Slack API client must satisfy:
   - `call(method, **kwargs)`: Generic dynamic method invocation.
   - `post_message(channel, text, thread_ts, **kwargs)`: Post message to a channel/thread.
   - `add_reaction(channel, timestamp, name, **kwargs)`: Add emoji reaction.
   - `get_conversation_replies(channel, ts, limit, **kwargs)`: Retrieve thread replies.
   - `auth_test(**kwargs)`: Test bot authentication and identity.

2. **Implementations**:
   - `SlackWebClient`: In-process HTTPS requests via official `slack_sdk.WebClient`
     using persistent HTTP keep-alive connection pooling.
   - `SlackCliClient`: Out-of-process subprocess execution via the official `slack api`
     CLI binary (`~/.slack/bin/slack`).

3. **Factory / Provider (`APIClientProvider`)**:
   Centralizes client instantiation. By default, it provides `SlackWebClient`.
   Clients can be toggled dynamically via parameter or `SLACK_API_CLIENT_TYPE` env var.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Protocol, runtime_checkable
from dotenv import load_dotenv

# Load local environment variables (.env)
load_dotenv()

# Configure module-level logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger: logging.Logger = logging.getLogger("SlackApiClient")


class SlackApiError(Exception):
    """Raised when an API call fails or returns an error response (`ok=False`)."""

    def __init__(self, error: str, raw_response: dict[str, Any] | None = None) -> None:
        super().__init__(f"Slack API error: {error}")
        self.error: str = error
        self.raw_response: dict[str, Any] = raw_response or {}


# ---------------------------------------------------------------------------
# 1. Protocol Abstraction (PEP 544 Structural Subtyping)
# ---------------------------------------------------------------------------

@runtime_checkable
class APIClient(Protocol):
    """Protocol defining the interface for Slack API clients.

    Any conforming implementation can be used interchangeably by the application
    layer without coupling to specific transport mechanisms.
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


# ---------------------------------------------------------------------------
# 2. Implementation 1: SlackWebClient (In-Process HTTPS)
# ---------------------------------------------------------------------------

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
        """Invoke an arbitrary Slack Web API method directly via HTTP."""
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


# ---------------------------------------------------------------------------
# 3. Implementation 2: SlackCliClient (Subprocess via `slack api`)
# ---------------------------------------------------------------------------

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
        # 1. Check system PATH
        path_from_shutil = shutil.which("slack")
        if path_from_shutil:
            return path_from_shutil

        # 2. Check standard Slack CLI install locations
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
        """Invoke an arbitrary Slack Web API method via the `slack api` CLI command."""
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


# ---------------------------------------------------------------------------
# 4. Factory Pattern: APIClientProvider
# ---------------------------------------------------------------------------

class APIClientProvider:
    """Factory provider that resolves and instantiates an `APIClient`.

    By default, it provides `SlackWebClient` for high-performance in-process HTTP.
    Alternatively, setting `client_type="cli"` or the `SLACK_API_CLIENT_TYPE=cli`
    environment variable provides `SlackCliClient`.
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
            client = SlackWebClient(token=token, **kwargs)
        elif resolved_type in ("cli", "slackcliclient", "slack_cli"):
            client = SlackCliClient(token=token, **kwargs)
        else:
            raise ValueError(
                f"Unknown client_type '{resolved_type}'. Expected 'web' or 'cli'."
            )

        # Static / runtime contract verification
        assert isinstance(client, APIClient), f"{client.__class__.__name__} must satisfy APIClient Protocol"
        return client


# ---------------------------------------------------------------------------
# 5. Diagnostic & Benchmark Utility
# ---------------------------------------------------------------------------

def compare_clients(method: str = "auth.test", **kwargs: Any) -> None:
    """Benchmark and compare Direct Web API vs Slack CLI for a given method call."""
    print("\n" + "=" * 70)
    print(f"SLACK API PROTOCOL BENCHMARK: method='{method}'")
    print("=" * 70)

    # 1. WebClient via Provider
    print("\n[Method 1: SlackWebClient via APIClientProvider]")
    try:
        web_client: APIClient = APIClientProvider.get_client("web")
        t0 = time.perf_counter()
        web_res = web_client.call(method, **kwargs)
        web_latency = (time.perf_counter() - t0) * 1000.0

        print(f"  Protocol : APIClient verified (isinstance: {isinstance(web_client, APIClient)})")
        print(f"  Status   : SUCCESS (ok=True)")
        print(f"  Latency  : {web_latency:.1f} ms")
        print(f"  User     : {web_res.get('user')}")
    except Exception as err:
        print(f"  Failed   : {err}")
        web_latency = None

    # 2. CliClient via Provider
    print("\n[Method 2: SlackCliClient via APIClientProvider]")
    try:
        cli_client: APIClient = APIClientProvider.get_client("cli")
        t0 = time.perf_counter()
        cli_res = cli_client.call(method, **kwargs)
        cli_latency = (time.perf_counter() - t0) * 1000.0

        print(f"  Protocol : APIClient verified (isinstance: {isinstance(cli_client, APIClient)})")
        print(f"  Status   : SUCCESS (ok=True)")
        print(f"  Latency  : {cli_latency:.1f} ms")
        print(f"  User     : {cli_res.get('user')}")
    except Exception as err:
        print(f"  Failed   : {err}")
        cli_latency = None

    # Summary
    print("\n" + "-" * 70)
    print("COMPARISON SUMMARY:")
    if web_latency is not None and cli_latency is not None:
        speedup = cli_latency / web_latency if web_latency > 0 else 0
        print(f"  SlackWebClient : {web_latency:7.1f} ms (In-process persistent HTTP)")
        print(f"  SlackCliClient : {cli_latency:7.1f} ms (External CLI subprocess)")
        print(f"  Speedup Ratio  : SlackWebClient is ~{speedup:.1f}x faster.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    compare_clients(method="auth.test")
