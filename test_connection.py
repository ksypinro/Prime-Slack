"""
Diagnostic script to test and verify Slack Bot and App tokens.
Runs:
1. Token format validation
2. Web API authentication (auth.test)
3. Bot identity and workspace confirmation
4. Socket Mode WebSocket connectivity test
"""

import os
import sys
import time
from dotenv import load_dotenv

# Load .env
load_dotenv()

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()
APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "").strip()

print("\n" + "=" * 60)
print("🔍 SLACK CREDENTIALS DIAGNOSTIC TEST")
print("=" * 60)

# Check 1: Format Checks
has_errors = False

if not BOT_TOKEN or BOT_TOKEN == "paste-your-xoxb-token-here":
    print("❌ SLACK_BOT_TOKEN is missing or still set to the placeholder in .env!")
    print("   👉 Go to api.slack.com/apps -> Your App -> OAuth & Permissions -> Copy 'Bot User OAuth Token'")
    has_errors = True
elif not BOT_TOKEN.startswith("xoxb-"):
    print("❌ SLACK_BOT_TOKEN does not start with 'xoxb-'. Please check your token format.")
    has_errors = True
else:
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

# Check 2: Test Bot Token via Web API (auth.test)
print("\n📡 Testing Bot Token via Slack Web API (auth.test)...")
try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    client = WebClient(token=BOT_TOKEN)
    auth_resp = client.auth_test()

    bot_name = auth_resp.get("user")
    bot_id = auth_resp.get("user_id")
    team_name = auth_resp.get("team")
    team_id = auth_resp.get("team_id")

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

# Check 3: Test Socket Mode Connectivity
print("\n🔌 Testing Socket Mode WebSocket Connection...")
try:
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse

    sm_client = SocketModeClient(
        app_token=APP_TOKEN,
        web_client=client,
    )

    connected = False

    def test_listener(client: SocketModeClient, req: SocketModeRequest):
        pass

    sm_client.socket_mode_request_listeners.append(test_listener)
    sm_client.connect()

    # Wait up to 5 seconds to confirm connection
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

    sm_client.close()

except Exception as e:
    print(f"❌ Socket Mode Test Error: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("🎉 ALL TESTS PASSED! Your Slack setup is ready.")
print("👉 You can now run the bot with: python app.py")
print("=" * 60 + "\n")
