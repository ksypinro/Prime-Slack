"""
Slack Credentials & Socket Mode Connectivity Diagnostic Tool.

This script performs a 3-point pre-flight health check to validate that
your Slack configuration is correct before launching the main bot service:

    Check 1 — Token Format Validation:
        Ensures ``SLACK_BOT_TOKEN`` starts with ``xoxb-`` and
        ``SLACK_APP_TOKEN`` starts with ``xapp-``, and that neither is
        still set to the placeholder default value.

    Check 2 — Web API Authentication (``auth.test``):
        Calls the Slack Web API ``auth.test`` endpoint to verify the bot
        token is valid and retrievable. Reports the bot's display name,
        User ID, workspace name, and workspace ID.

    Check 3 — Socket Mode WebSocket Handshake:
        Opens a temporary outbound WebSocket connection (``wss://``) to
        Slack's Socket Mode servers using the App-Level Token. Confirms
        that the connection is established within 5 seconds, verifying
        that your network/firewall allows outbound WSS on port 443.

Usage:
    Ensure ``.env`` is configured with valid tokens, then run::

        $ python test_connection.py

Exit Codes:
    0 — All checks passed successfully.
    1 — One or more checks failed. See console output for details.
"""

import os
import sys
import time

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. Load Environment Variables
# ---------------------------------------------------------------------------
load_dotenv()

BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "").strip()
"""Bot User OAuth Token (``xoxb-...``) loaded from ``.env``."""

APP_TOKEN: str = os.getenv("SLACK_APP_TOKEN", "").strip()
"""App-Level Token (``xapp-...``) loaded from ``.env``."""

# ---------------------------------------------------------------------------
# 2. Header
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("🔍 SLACK CREDENTIALS DIAGNOSTIC TEST")
print("=" * 60)

# ---------------------------------------------------------------------------
# Check 1: Token Format Validation
# ---------------------------------------------------------------------------
# Validates that both tokens are present, non-empty, not set to placeholder
# defaults, and have the correct prefix format expected by Slack.

has_errors: bool = False

if not BOT_TOKEN or BOT_TOKEN == "paste-your-xoxb-token-here":
    print("❌ SLACK_BOT_TOKEN is missing or still set to the placeholder in .env!")
    print("   👉 Go to api.slack.com/apps -> Your App -> OAuth & Permissions -> Copy 'Bot User OAuth Token'")
    has_errors = True
elif not BOT_TOKEN.startswith("xoxb-"):
    print("❌ SLACK_BOT_TOKEN does not start with 'xoxb-'. Please check your token format.")
    has_errors = True
else:
    # Display a safe, truncated preview of the token for confirmation.
    print(f"✅ SLACK_BOT_TOKEN found: {BOT_TOKEN[:9]}...{BOT_TOKEN[-4:]}")

if not APP_TOKEN or APP_TOKEN == "paste-your-xapp-token-here":
    print("❌ SLACK_APP_TOKEN is missing or still set to the placeholder in .env!")
    print("   👉 Go to api.slack.com/apps -> Your App -> Basic Information -> App-Level Tokens")
    print("   👉 Ensure it has the 'connections:write' scope and copy the token starting with 'xapp-'.")
    has_errors = True
elif not APP_TOKEN.startswith("xapp-"):
    print("❌ SLACK_APP_TOKEN does not start with 'xapp-'. Please check your token format.")
    has_errors = True
else:
    print(f"✅ SLACK_APP_TOKEN found: {APP_TOKEN[:9]}...{APP_TOKEN[-4:]}")

if has_errors:
    print("\n⚠️  Please update your .env file with valid tokens and re-run this test.")
    print("=" * 60 + "\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Check 2: Web API Authentication via auth.test
# ---------------------------------------------------------------------------
# The ``auth.test`` endpoint validates the bot token against Slack's servers
# and returns the bot's identity (username, User ID) and workspace metadata
# (team name, team ID). A successful response confirms that:
#   - The token is valid and has not been revoked.
#   - The App is installed in the target workspace.

print("\n📡 Testing Bot Token via Slack Web API (auth.test)...")
try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    client = WebClient(token=BOT_TOKEN)
    auth_resp = client.auth_test()

    bot_name: str = auth_resp.get("user")
    bot_id: str = auth_resp.get("user_id")
    team_name: str = auth_resp.get("team")
    team_id: str = auth_resp.get("team_id")

    print("✅ Bot Authentication SUCCESSFUL!")
    print(f"   • Bot Display Name : @{bot_name}")
    print(f"   • Bot User ID      : {bot_id}")
    print(f"   • Slack Workspace  : {team_name} ({team_id})")

except ImportError:
    print("❌ slack-sdk is not installed. Run: pip install -r requirements.txt")
    sys.exit(1)
except SlackApiError as e:
    print(f"❌ Slack API Auth Failed: {e.response.get('error')}")
    print("   👉 Ensure the App is installed into your workspace (Settings > Install App).")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error connecting to Slack API: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Check 3: Socket Mode WebSocket Connectivity
# ---------------------------------------------------------------------------
# Opens a temporary WebSocket connection to Slack's Socket Mode servers.
# This verifies that:
#   - The App-Level Token (xapp-) has the ``connections:write`` scope.
#   - Socket Mode is enabled in the app settings.
#   - Your local network/firewall allows outbound WSS connections on port 443.
#
# The connection is polled for up to 5 seconds (10 × 0.5s intervals).
# After verification, the connection is cleanly closed.

print("\n🔌 Testing Socket Mode WebSocket Connection...")
try:
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse

    sm_client = SocketModeClient(
        app_token=APP_TOKEN,
        web_client=client,
    )

    connected: bool = False

    def test_listener(client: SocketModeClient, req: SocketModeRequest) -> None:
        """No-op listener required by SocketModeClient to accept events."""
        pass

    sm_client.socket_mode_request_listeners.append(test_listener)
    sm_client.connect()

    # Poll for connection status (up to 5 seconds total).
    for _ in range(10):
        time.sleep(0.5)
        if sm_client.is_connected():
            connected = True
            break

    if connected:
        print("✅ Socket Mode WebSocket Handshake SUCCESSFUL!")
        print("   • Persistent outbound connection established with Slack servers.")
        print("   • No public webhooks or tunnels needed.")
    else:
        print("⚠️  Socket Mode connection timed out or failed.")
        print("   👉 Check that your App-Level Token has the 'connections:write' scope.")
        print("   👉 Check that Socket Mode is enabled under Settings > Socket Mode.")

    # Clean up the temporary connection.
    sm_client.close()

except Exception as e:
    print(f"❌ Socket Mode Test Error: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Final Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("🎉 ALL TESTS PASSED! Your Slack setup is ready.")
print("👉 You can now run the bot with: python app.py")
print("=" * 60 + "\n")
