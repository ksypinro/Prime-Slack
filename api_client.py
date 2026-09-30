"""
Slack API Client — Dual-Mode HTTP Request Dispatcher.

This module demonstrates and implements two distinct methods of communicating
with the Slack Web API:

1. **Direct Slack Web API (In-Process HTTP via `slack_sdk.WebClient`)**:
   - Sends outbound HTTPS requests directly from the Python runtime to
     `https://slack.com/api/{method}` using an in-memory HTTP client.
   - Ideal for low-latency production applications, bots, and high-throughput event handlers.

2. **Slack CLI Subprocess (`slack api <method>`)**:
   - Executes the official Slack CLI binary as an external subprocess, passing
     arguments and parsing the resulting stdout JSON.
   - Ideal for shell scripts, DevOps pipelines, CI/CD runners, and ad-hoc terminal diagnostics.

Both clients implement a unified interface, allowing you to seamlessly swap or
benchmark between in-process HTTP and CLI-based API execution.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, Optional
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
    """Raised when an API call returns an unsuccessful response (ok=False)."""

    def __init__(self, error: str, raw_response: dict[str, Any] | None = None) -> None:
        super().__init__(f"Slack API error: {error}")
        self.error: str = error
        self.raw_response: dict[str, Any] | None = raw_response or {}


class DirectWebClient:
    """Sends HTTP requests directly to the Slack Web API using the Python SDK.

    This client maintains an in-process HTTP session and executes direct HTTPS
    POST/GET requests to `https://slack.com/api/{method}` with:
        - `Authorization: Bearer <xoxb-...>`
        - `Content-Type: application/json; charset=utf-8`

    Attributes:
        token (str): The Slack Bot or User OAuth token.
        client (WebClient): The underlying slack_sdk WebClient instance.
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

        # Import lazily to avoid overhead if only CLI is desired
        from slack_sdk import WebClient
        self.client: WebClient = WebClient(token=self.token)

    def call(self, method: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke any Slack Web API method directly via HTTP.

        Args:
            method: The Slack API method name (e.g., 'auth.test', 'chat.postMessage').
            **kwargs: Parameters passed to the method as keyword arguments.

        Returns:
            dict: The parsed JSON dictionary response from Slack.

        Raises:
            SlackApiError: If Slack returns `{"ok": false, "error": ...}`.
        """
        from slack_sdk.errors import SlackApiError as SdkApiError

        try:
            # api_call allows arbitrary method invocations dynamically
            response = self.client.api_call(api_method=method, json=kwargs if kwargs else None)
            data: dict[str, Any] = response.data  # type: ignore[assignment]
            if not data.get("ok"):
                raise SlackApiError(error=data.get("error", "unknown_error"), raw_response=data)
            return data
        except SdkApiError as err:
            error_code = err.response.get("error", str(err))
            raise SlackApiError(error=error_code, raw_response=err.response.data) from err


class CliApiClient:
    """Sends requests to the Slack API by invoking the `slack api` CLI command.

    This client locates the Slack CLI binary (`slack`) on the host system and executes:
        `slack api <method> --json '<payload>' --token <token>`

    Attributes:
        token (str): The Slack Bot or User OAuth token.
        cli_path (str): The resolved absolute path to the `slack` executable.
    """

    def __init__(self, token: str | None = None, cli_path: str | None = None) -> None:
        """Initialize the CLI-based API client.

        Args:
            token: Slack Bot or User token. Defaults to `SLACK_BOT_TOKEN`.
            cli_path: Explicit path to the `slack` executable. If omitted,
                      automatically discovers it via system PATH or `~/.slack/bin/slack`.
        """
        self.token: str = token or os.environ.get("SLACK_BOT_TOKEN", "")
        self.cli_path: str = cli_path or self._resolve_cli_path()

    @staticmethod
    def _resolve_cli_path() -> str:
        """Locate the Slack CLI binary across known install locations.

        Returns:
            str: Absolute path to the `slack` executable.

        Raises:
            FileNotFoundError: If the Slack CLI binary cannot be found.
        """
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
        """Invoke any Slack Web API method via the `slack api` CLI command.

        Args:
            method: The Slack API method name (e.g., 'auth.test', 'chat.postMessage').
            **kwargs: Parameters passed to the method. Serialized as JSON.

        Returns:
            dict: The parsed JSON response emitted on stdout by the Slack CLI.

        Raises:
            SlackApiError: If the CLI returns a non-zero exit code or Slack reports ok=False.
        """
        cmd: list[str] = [self.cli_path, "api", method]

        # Pass token if available
        if self.token:
            cmd.extend(["--token", self.token])

        # Pass arguments as a JSON payload flag
        if kwargs:
            cmd.extend(["--json", json.dumps(kwargs)])

        logger.debug("Executing CLI command: %s", " ".join(cmd))

        # Run external process synchronously and capture output
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
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
                raw_response={"stdout": stdout_clean, "stderr": stderr_clean}
            ) from json_err

        if not data.get("ok"):
            raise SlackApiError(error=data.get("error", "cli_api_error"), raw_response=data)

        return data


def compare_clients(method: str = "auth.test", **kwargs: Any) -> None:
    """Benchmark and compare Direct Web API vs Slack CLI for a given method call.

    Args:
        method: The Slack API method to test (e.g. 'auth.test').
        **kwargs: Arguments to pass to the method.
    """
    print("\n" + "=" * 70)
    print(f"SLACK API COMPARISON BENCHMARK: method='{method}'")
    print("=" * 70)

    # 1. Direct Web API Test
    print("\n[Method 1: Direct Slack Web API (Python SDK / In-Process HTTPS)]")
    try:
        web_client = DirectWebClient()
        start_time = time.perf_counter()
        web_res = web_client.call(method, **kwargs)
        web_latency = (time.perf_counter() - start_time) * 1000.0

        print(f"  Status   : SUCCESS (ok=True)")
        print(f"  Latency  : {web_latency:.1f} ms")
        print(f"  Response : {json.dumps(web_res, indent=2)}")
    except Exception as err:
        print(f"  Failed   : {err}")
        web_latency = None

    # 2. Slack CLI Subprocess Test
    print("\n[Method 2: Slack CLI Subprocess (`slack api` command)]")
    try:
        cli_client = CliApiClient()
        print(f"  Binary   : {cli_client.cli_path}")
        start_time = time.perf_counter()
        cli_res = cli_client.call(method, **kwargs)
        cli_latency = (time.perf_counter() - start_time) * 1000.0

        print(f"  Status   : SUCCESS (ok=True)")
        print(f"  Latency  : {cli_latency:.1f} ms")
        print(f"  Response : {json.dumps(cli_res, indent=2)}")
    except Exception as err:
        print(f"  Failed   : {err}")
        cli_latency = None

    # Summary
    print("\n" + "-" * 70)
    print("COMPARISON SUMMARY:")
    if web_latency is not None and cli_latency is not None:
        speedup = cli_latency / web_latency if web_latency > 0 else 0
        print(f"  Direct Web API : {web_latency:7.1f} ms (Persistent HTTPS session, zero process overhead)")
        print(f"  Slack CLI      : {cli_latency:7.1f} ms (External Go binary spawn + handshake per call)")
        print(f"  Performance    : Direct Web API is ~{speedup:.1f}x faster for real-time operations.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    compare_clients(method="auth.test")
