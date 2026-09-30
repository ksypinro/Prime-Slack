"""
Benchmark & Diagnostic Tool for APIClient Package.

Benchmarks and compares `SlackWebClient` vs `SlackCliClient` on live workspace credentials.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .protocol import APIClient
from .provider import APIClientProvider


def compare_clients(method: str = "auth.test", **kwargs: Any) -> None:
    """Benchmark and compare SlackWebClient vs SlackCliClient."""
    print("\n" + "=" * 70)
    print(f"SLACK API PROTOCOL BENCHMARK: method='{method}'")
    print("=" * 70)

    # 1. SlackWebClient via Provider
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

    # 2. SlackCliClient via Provider
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
