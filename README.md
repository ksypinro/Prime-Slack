# Slack Socket Mode Bot & Context Observer

An enterprise-ready, firewall-friendly Python application that observes Slack workspace events in real time, extracts conversation thread context, and performs automated actions without requiring public webhooks, domain names, or reverse proxy tunnels (such as ngrok).

---

## Table of Contents
- [Architecture & Overview](#architecture--overview)
- [Why Socket Mode Instead of Public Webhooks?](#why-socket-mode-instead-of-public-webhooks)
- [Prerequisites](#prerequisites)
- [Step 1: Install the Slack CLI](#step-1-install-the-slack-cli)
- [Step 2: Create the Slack App](#step-2-create-the-slack-app)
- [Step 3: Collect the App-Level Token (`xapp-...`)](#step-3-collect-the-app-level-token-xapp-)
- [Step 4: Configure Bot Scopes & Collect Bot Token (`xoxb-...`)](#step-4-configure-bot-scopes--collect-bot-token-xoxb-)
- [Step 5: Project Setup & Environment Configuration](#step-5-project-setup--environment-configuration)
- [Step 6: Diagnostic Verification & Execution](#step-6-diagnostic-verification--execution)
- [Deep Dive: Lifecycle, Code Flow & API Mechanics](#deep-dive-lifecycle-code-flow--api-mechanics)
- [Customizing the Analysis Logic (`processor.py`)](#customizing-the-analysis-logic-processorpy)
- [Project Structure](#project-structure)

---

## Architecture & Overview

```
                                  FIREWALL BOUNDARY
                                         │
┌─────────────────────────┐              │          ┌──────────────────────────────────┐
│       Slack Cloud       │              │          │     Local Machine (Your PC)      │
│                         │              │          │                                  │
│  User mentions @Bot in  │              │          │   app.py (Socket Mode Listener)  │
│  channel or thread      │              │          │                                  │
│            │            │              │          │                                  │
│            ▼            │              │          │                                  │
│   Events API Engine     │              │          │                                  │
│            │            │              │          │                                  │
│            ▼            │  WSS (443)   │          │                                  │
│     WebSocket Server    ├──────────────┼─────────►│ 1. Receives `app_mention` event  │
│                         │ (Persistent  │          │    via WebSocket frame           │
│                         │  outbound)   │          │                                  │
│                         │              │          │ 2. Adds 👀 reaction (:eyes:)     │
│   Web API REST Endpoints│              │          │    via Web API                   │
│   (https://slack.com)   │              │          │                                  │
│            ▲            │  HTTPS (443) │          │ 3. Fetches full thread history   │
│            │◄───────────┼──────────────┼──────────┤    via `conversations.replies`   │
│            │            │              │          │                                  │
│            │            │              │          │ 4. Passes context to processor.py│
│            │            │              │          │    (LLM / Custom Script)         │
│            │            │  HTTPS (443) │          │                                  │
│            │◄───────────┼──────────────┼──────────┤ 5. Posts reply inside thread     │
│                         │              │          │    via `chat.postMessage`        │
│                         │              │          │                                  │
│                         │              │          │ 6. Adds ✅ reaction on done      │
└─────────────────────────┘              │          └──────────────────────────────────┘
                                         │
```

---

## Why Socket Mode Instead of Public Webhooks?

Traditional Slack integrations rely on **HTTP Webhooks**:
- Slack requires an externally accessible, public HTTPS URL (e.g., `https://your-domain.com/slack/events`).
- Developing locally requires exposing your computer through tunneling software (such as ngrok), which introduces network vulnerability, dynamic URLs that change on every restart, and corporate firewall blockers.

**Socket Mode eliminates this entirely:**
- Your machine initiates a secure, **outbound WebSocket connection** (`wss://wss-primary.slack.com/...`) on standard HTTPS port 443.
- Because the connection is outbound, **firewalls and NAT routers allow it automatically**.
- No ports are opened on your local machine, and no public URLs or reverse proxies are needed.

---

## Prerequisites

1. **Python 3.10+** installed on your system.
2. A **Slack Workspace** where you have permission to install apps (you can create a free workspace at [slack.com/get-started](https://slack.com/get-started)).
3. **Slack CLI** (Optional, but recommended for app lifecycle management).

---

## Step 1: Install the Slack CLI

The Slack CLI allows you to scaffold apps, manage manifests, validate configurations, and run local development servers.

### macOS (via Homebrew)
```bash
brew install slack-cli
```

### Linux / Windows (WSL)
```bash
curl -fsSL https://downloads.slack-edge.com/slack-cli/install.sh | bash
```

### Authenticate the CLI with Your Workspace
```bash
slack login
```
Follow the browser prompt to log into your Slack workspace and authorize the CLI.

---

## Step 2: Create the Slack App

You can create the app in under 60 seconds using the preconfigured [`manifest.json`](manifest.json) included in this repository.

1. Go to the [Slack App Management Portal](https://api.slack.com/apps).
2. Click **Create New App**.
3. In the popup dialog, choose **From an app manifest**.
4. Select your target Slack workspace and click **Next**.
5. Select the **JSON** tab, copy the contents of [`manifest.json`](manifest.json), and paste them into the box:

```json
{
  "_comment": "Slack App Manifest for Prime Bot (Socket Mode)",
  "display_information": {
    "name": "Prime",
    "description": "Local observation bot connected via Socket Mode",
    "background_color": "#1A1D21"
  },
  "features": {
    "bot_user": {
      "display_name": "Prime",
      "always_online": true
    }
  },
  "oauth_config": {
    "scopes": {
      "bot": [
        "app_mentions:read",
        "channels:history",
        "groups:history",
        "im:history",
        "mpim:history",
        "chat:write",
        "reactions:write",
        "users:read"
      ]
    }
  },
  "settings": {
    "socket_mode_enabled": true,
    "event_subscriptions": {
      "bot_events": [
        "app_mention",
        "message.im"
      ]
    },
    "org_deploy_enabled": false
  }
}
```
6. Click **Next** and then click **Create**.

---

## Step 3: Collect the App-Level Token (`xapp-...`)

The App-Level Token controls the WebSocket connection (Socket Mode) between your local PC and Slack.

1. Inside your app's dashboard at [api.slack.com/apps](https://api.slack.com/apps), navigate to **Settings** > **Basic Information** (left sidebar).
2. Scroll down to the section titled **App-Level Tokens** and click **Generate Token and Scopes** (or select your existing token).
3. Set the **Token Name** to: `SocketModeToken`.
4. Click **Add Scope** and select:
   - `connections:write`
5. Click **Generate**.
6. Copy the token. It starts with **`xapp-`** (e.g., `xapp-1-A0C5...`).

---

## Step 4: Configure Bot Scopes & Collect Bot Token (`xoxb-...`)

The Bot Token provides identity to the bot user inside your workspace, granting it permission to read messages, post replies, and add emoji reactions.

1. Navigate to **Settings** > **Install App** (or **OAuth & Permissions**).
2. Click the green button: **Install to Workspace** (or **Reinstall to Workspace**).
3. Review the requested permissions (`app_mentions:read`, `chat:write`, `channels:history`, etc.) and click **Allow**.
4. Once installed, copy the **Bot User OAuth Token**.
   - It begins with **`xoxb-`** (e.g., `xoxb-1219...`).

---

## Step 5: Project Setup & Environment Configuration

1. **Clone this repository:**
   ```bash
   git clone <your-repository-url>
   cd "Slack CLI"
   ```

2. **Create and activate a Python virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your secrets in `.env`:**
   Copy the example file:
   ```bash
   cp .env.example .env
   ```
   Open `.env` in your text editor and paste your collected tokens:
   ```env
   # Bot User OAuth Token
   SLACK_BOT_TOKEN=xoxb-your-actual-bot-token

   # App-Level Token with connections:write scope
   SLACK_APP_TOKEN=xapp-your-actual-app-token

   # Logging verbosity (DEBUG, INFO, WARNING, ERROR)
   LOG_LEVEL=INFO
   ```

> **Security Note:** The `.env` file is explicitly ignored in `.gitignore`. Never commit your real tokens to any Git repository.

---

## Step 6: Diagnostic Verification & Execution

### 1. Run the Diagnostic Test
Before launching the service, verify your credentials and network connection using the automated diagnostic tool:

```bash
python test_connection.py
```

The script performs a 3-point health check:
1. Validates token format integrity (`xoxb-` and `xapp-`).
2. Calls Slack Web API `auth.test` to verify your workspace name, bot username, and User ID.
3. Establishes a temporary WebSocket handshake over Socket Mode to confirm outbound connectivity.

Expected output:
```text
============================================================
🔍 SLACK CREDENTIALS DIAGNOSTIC TEST
============================================================
✅ SLACK_BOT_TOKEN found: xoxb-1219...
✅ SLACK_APP_TOKEN found: xapp-1-A0...

📡 Testing Bot Token via Slack Web API (auth.test)...
✅ Bot Authentication SUCCESSFUL!
   • Bot Display Name : @Prime
   • Bot User ID      : U0C5NJVTXAA
   • Slack Workspace  : MyWorkspace (T0C5...)

🔌 Testing Socket Mode WebSocket Connection...
✅ Socket Mode WebSocket Handshake SUCCESSFUL!
   • Persistent outbound connection established with Slack servers.
   • No public webhooks or tunnels needed.

============================================================
🎉 ALL TESTS PASSED! Your Slack setup is ready.
============================================================
```

### 2. Start the Bot Service
```bash
python app.py
```

### 3. Test in Slack
1. Go to any channel in your Slack workspace and invite your bot:
   ```text
   /invite @Prime
   ```
2. Mention the bot in a channel or within an existing reply thread:
   ```text
   @Prime please summarize the status discussed in this thread.
   ```
3. Watch the automated cycle happen live:
   - The bot adds a `👀` emoji reaction immediately.
   - It fetches the conversation history in the thread.
   - It processes the text via [`processor.py`](processor.py).
   - It posts the reply inside the thread.
   - It swaps/adds the `✅` emoji reaction upon completion.

---

## Deep Dive: Lifecycle, Code Flow & API Mechanics

### 1. Event Ingestion via Socket Mode
When a user types `@Prime ...`:
1. Slack identifies that an event matching the `app_mention` subscription occurred.
2. Instead of performing an HTTP POST to an external server, Slack formats a JSON payload and pushes it as a text frame across the open WebSocket (`wss://`) connection maintained by `SocketModeHandler`.
3. The local Bolt framework instantly sends an acknowledgment frame (`{"envelope_id": "...", "payload": {}}`) back across the socket. This satisfies Slack's strict 3-second timeout requirement.

### 2. Event Payload Parsing
The `handle_app_mention` function receives the event dictionary:
```python
channel_id = event["channel"]                    # e.g., "C0123456789"
message_ts = event["ts"]                         # Timestamp of the mention message itself
thread_ts  = event.get("thread_ts", message_ts)  # Parent thread timestamp
user_id    = event["user"]                       # User who mentioned the bot
```

#### Determining Thread vs. Channel Context:
* **Inside an existing thread:** Slack populates `event["thread_ts"]` with the timestamp of the thread's root parent message.
* **Top-level channel message:** `event.get("thread_ts")` is `None`. By falling back to `message_ts`, any subsequent reply posted using `thread_ts=message_ts` automatically creates a neat, threaded conversation originating from the user's mention.

### 3. Visual Feedback (User Experience)
```python
client.reactions_add(channel=channel_id, name="eyes", timestamp=message_ts)
```
Calling `reactions.add` gives the user instant visual confirmation that the bot is running their task.

### 4. Fetching Thread Context
```python
history_response = client.conversations_replies(channel=channel_id, ts=thread_ts, limit=50)
thread_messages = history_response.get("messages", [])
```
Unlike standard bots that only read the single trigger message, `conversations.replies` pulls up to 50 previous messages from the thread, giving your analysis logic full conversational memory.

### 5. Replying Back into the Thread
```python
client.chat_postMessage(
    channel=channel_id,
    thread_ts=thread_ts,   # Keeps the conversation tidy inside the thread
    text=reply_content
)
```
Setting `thread_ts` ensures the bot's reply does not flood the main channel.

---

## Customizing the Analysis Logic (`processor.py`)

All task processing and context analysis is isolated inside [`processor.py`](processor.py). You can plug in any AI provider or internal automation script:

### Example: Connecting OpenAI / Anthropic / Gemini
```python
import openai

def process_thread_context(thread_messages, triggering_user, triggering_text):
    # 1. Format the conversation for the LLM
    conversation_text = "\n".join([f"User: {m.get('text')}" for m in thread_messages])
    
    # 2. Call your model
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant analyzing a Slack thread."},
            {"role": "user", "content": f"Context:\n{conversation_text}\n\nTask: {triggering_text}"}
        ]
    )
    return response.choices[0].message.content
```

---

## Project Structure

```
.
├── app.py                 # Core Bolt app — Socket Mode event listener & dispatcher
├── processor.py           # Pluggable thread context analyzer (LLM / automation hook)
├── test_connection.py     # 3-point diagnostic: token format, auth.test, WSS handshake
├── manifest.json          # Pre-configured Slack App Manifest (importable at api.slack.com)
├── requirements.txt       # Python dependencies (slack-bolt, slack-sdk, python-dotenv)
├── .env.example           # Safe template for credentials (never commit .env itself)
├── .gitignore             # Safeguards secrets, venv, cache, and editor metadata
├── LICENSE                # MIT License
├── CONTRIBUTING.md        # Contributor guidelines and PR workflow
├── CODE_OF_CONDUCT.md     # Contributor Covenant v2.1
├── SECURITY.md            # Vulnerability disclosure policy & token security practices
└── README.md              # This file — setup, architecture, and usage documentation
```

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

## License

This project is licensed under the [MIT License](LICENSE). Feel free to use and adapt it for personal or enterprise Slack workflows.
