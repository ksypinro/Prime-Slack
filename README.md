# Slack Socket Mode Bot & Context Observer

An enterprise-ready, firewall-friendly Python application that observes Slack workspace events in real time, extracts conversation thread context, and performs automated actions — without requiring public webhooks, domain names, or reverse proxy tunnels (such as ngrok).

---

## Table of Contents

- [Understanding Slack's Architecture](#understanding-slacks-architecture)
  - [What is a Slack App?](#what-is-a-slack-app)
  - [What is a Bot?](#what-is-a-bot)
  - [The Three Token Types](#the-three-token-types)
  - [What is the Slack Web API?](#what-is-the-slack-web-api)
  - [What is the Slack CLI?](#what-is-the-slack-cli)
- [How Event Delivery Works (Webhooks vs. Socket Mode)](#how-event-delivery-works-webhooks-vs-socket-mode)
  - [The Traditional Webhook Approach (And Its Problems)](#the-traditional-webhook-approach-and-its-problems)
  - [Socket Mode: The Firewall-Friendly Alternative](#socket-mode-the-firewall-friendly-alternative)
- [Architecture of This Project](#architecture-of-this-project)
- [Prerequisites](#prerequisites)
- [Step 1: Install the Slack CLI](#step-1-install-the-slack-cli)
- [Step 2: Create the Slack App](#step-2-create-the-slack-app)
- [Step 3: Collect the App-Level Token (`xapp-...`)](#step-3-collect-the-app-level-token-xapp-)
- [Step 4: Install the App & Collect Bot Token (`xoxb-...`)](#step-4-install-the-app--collect-bot-token-xoxb-)
- [Step 5: Project Setup & Environment Configuration](#step-5-project-setup--environment-configuration)
- [Step 6: Diagnostic Verification & Execution](#step-6-diagnostic-verification--execution)
- [Deep Dive: Lifecycle, Code Flow & API Mechanics](#deep-dive-lifecycle-code-flow--api-mechanics)
- [Customizing the Analysis Logic (`processor.py`)](#customizing-the-analysis-logic-processorpy)
- [Project Structure](#project-structure)

---

## Understanding Slack's Architecture

Before touching any code, it's important to understand how Slack's platform is structured. Slack is not just a chat application — it's an **extensible platform** with a well-defined security model. If you're coming from a background where you'd expect to just generate a personal API key from your profile settings, Slack works differently.

### What is a Slack App?

A **Slack App** is the **administrative container** for any programmatic integration with Slack. Think of it as a "project registration" on Slack's platform.

An App is **not** something users see or interact with directly. It's a configuration blueprint that defines:
- **What permissions** the integration requests (called "scopes" — e.g., permission to read messages, post replies, add emoji reactions).
- **What events** the integration listens to (e.g., "notify me whenever someone @mentions my bot").
- **How it connects** to Slack (Socket Mode via WebSocket, or traditional HTTP webhooks).
- **Client credentials** (Client ID, Client Secret) for OAuth authentication.

You create an App at [api.slack.com/apps](https://api.slack.com/apps). Once created, the App must be **installed** into a specific Slack Workspace by an administrator, who reviews and approves the requested permissions.

### What is a Bot?

A **Bot** (Bot User) is a **feature inside an App**. When you enable the "Bot User" feature in your App configuration, Slack creates a synthetic user account in your workspace:

- It has a **display name** and avatar (e.g., `@Prime`).
- It has its own unique **User ID** (e.g., `U0C5NJVTXAA`).
- It shows an **[APP]** badge next to its name in the member list.
- People can **invite** it to channels (`/invite @Prime`), **@mention** it, and **DM** it.

The relationship between App and Bot:

```
┌────────────────────────────────────────────────────────┐
│                     SLACK APP                          │
│  (The administrative container you create on           │
│   api.slack.com — defines permissions, events,         │
│   connection mode, and credentials)                    │
│                                                        │
│   ┌────────────────────────────────────────────────┐   │
│   │              BOT USER (@Prime)                 │   │
│   │  (A virtual member in your workspace that      │   │
│   │   your code controls — has a username, avatar, │   │
│   │   User ID, and can join channels, post msgs)   │   │
│   └────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

> **Key insight:** All Bots belong to an App, but an App can exist without a Bot (e.g., an App that only provides slash commands or workflow steps).

### The Three Token Types

When you set up a Slack App, you'll encounter three types of tokens. Each serves a different purpose:

| Token Prefix | Name | What It Represents | What It Can Do |
| :--- | :--- | :--- | :--- |
| `xapp-...` | **App-Level Token** | The App itself (not any specific user or bot) | Establishes the WebSocket connection for Socket Mode. Cannot read messages or post anything. |
| `xoxb-...` | **Bot Token** | The Bot User (`@Prime`) | Posts messages, reads channel history, adds emoji reactions — only within the scopes granted to the App. |
| `xoxp-...` | **User Token** (optional) | A real human user | Acts on behalf of the human who installed the App (e.g., setting their personal status). Not used in this project. |

**Why can't you just get a personal API key from your profile?**

Slack deprecated personal API tokens years ago for security reasons. Every token must now flow through an App because:
1. **Scoped permissions:** An App declares exactly what it can do (e.g., *only* `chat:write` and `app_mentions:read`). A leaked token can't access anything beyond those scopes.
2. **Admin governance:** Workspace administrators must review and approve every App's permissions before installation. Without Apps, there would be zero visibility into what scripts access company conversations.
3. **Auditability:** Bot tokens create actions under a distinct `[APP]` identity, so audit logs clearly separate human activity from automated activity.

### What is the Slack Web API?

The **Slack Web API** is a collection of RESTful HTTP endpoints hosted at `https://slack.com/api/`. Your code calls these endpoints (authenticated with a Bot Token) to **perform actions** in Slack:

| API Method | What It Does |
| :--- | :--- |
| `chat.postMessage` | Posts a message to a channel or thread |
| `conversations.replies` | Fetches all messages in a specific thread |
| `reactions.add` | Adds an emoji reaction to a message |
| `users.info` | Retrieves profile information for a user |
| `auth.test` | Verifies that a token is valid and returns identity info |

These are standard outbound HTTPS requests from your machine to Slack's servers — no different from calling any other REST API.

### What is the Slack CLI?

The **Slack CLI** (`slack`) is an optional command-line tool for managing App lifecycle tasks from your terminal instead of the web dashboard:

| CLI Command | Dashboard Equivalent |
| :--- | :--- |
| `slack login` | Logging into [api.slack.com](https://api.slack.com) |
| `slack create my-bot` | Creating a new App from a template |
| `slack manifest validate` | Checking your App manifest for errors |
| `slack run` | Starting a local development server with hot-reload |
| `slack deploy` | Deploying to Slack's hosted infrastructure |

**The Slack CLI is not required for this project.** You can create and configure the App entirely through the web dashboard at [api.slack.com/apps](https://api.slack.com/apps). The CLI is a convenience tool, not a dependency.

---

## How Event Delivery Works (Webhooks vs. Socket Mode)

This is the most critical concept to understand. When something happens in Slack (a user posts a message, @mentions your bot, reacts to a message), Slack needs a way to **notify your code**. There are two mechanisms:

### The Traditional Webhook Approach (And Its Problems)

In the traditional model, you provide Slack with a **public HTTPS URL** (e.g., `https://your-server.com/slack/events`). When an event occurs, Slack sends an HTTP POST request to that URL containing the event data:

```
┌───────────────┐         HTTP POST          ┌──────────────────────┐
│  Slack Cloud  │ ──────────────────────────► │  Your Public Server  │
│               │  {"type": "app_mention",   │  (https://...)       │
│               │   "channel": "C0123...",   │                      │
│               │   "text": "@Prime help"}   │  Must be reachable   │
│               │                            │  from the internet!  │
└───────────────┘                            └──────────────────────┘
```

**The problems with this approach:**
- You need a **public domain name** and HTTPS certificate.
- For local development, you need a **tunneling service** like ngrok (`https://xxxx.ngrok-free.app`) to expose your local machine to the internet.
- Corporate **firewalls block inbound connections**, making this impossible in many office environments.
- Ngrok URLs **change on every restart** and the free tier has rate limits.

### Socket Mode: The Firewall-Friendly Alternative

Socket Mode **reverses the connection direction**. Instead of Slack pushing HTTP requests to your server, **your machine pulls events from Slack** over a persistent outbound WebSocket:

```
┌───────────────┐                            ┌──────────────────────┐
│  Slack Cloud  │                            │  Your Local Machine  │
│               │                            │                      │
│   WebSocket   │ ◄─── wss:// (port 443) ─── │  SocketModeHandler   │
│    Server     │ ───  event JSON frames ──► │  (outbound conn)     │
│               │                            │                      │
│               │                            │  No open ports!      │
│               │                            │  No public URL!      │
│               │                            │  No ngrok!           │
└───────────────┘                            └──────────────────────┘
       ▲                                              │
       │          HTTPS REST (port 443)               │
       └──────────────────────────────────────────────┘
         Your code calls Web API methods
         (chat.postMessage, conversations.replies)
         using standard outbound HTTPS requests
```

**Why this works behind any firewall:**
1. Your machine initiates an **outbound** connection to `wss://wss-primary.slack.com` on port 443.
2. Port 443 outbound is almost universally allowed by firewalls (it's the same port used for HTTPS/browsing).
3. The WebSocket stays open persistently — Slack pushes event frames down this connection as they occur.
4. When your code needs to call Web API methods (posting a message, fetching history), it makes standard outbound HTTPS calls — also on port 443.
5. **Zero inbound ports or public URLs are ever required.**

---

## Architecture of This Project

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

**Two communication channels are at play (both outbound from your machine):**

1. **WebSocket (`wss://`, port 443)** — A persistent, bidirectional connection used *only* for event delivery. Slack pushes event JSON frames to your machine; your code sends acknowledgment frames back. Managed by `SocketModeHandler` using the `xapp-` token.

2. **HTTPS REST (`https://slack.com/api/`, port 443)** — Standard request/response API calls your code makes to perform actions (post messages, fetch threads, add reactions). Authenticated with the `xoxb-` bot token.

---

## Prerequisites

1. **Python 3.10+** installed on your system.
2. A **Slack Workspace** where you have permission to install apps (you can create a free workspace at [slack.com/get-started](https://slack.com/get-started)).
3. **Slack CLI** (Optional — the App can be created entirely through the web dashboard).

---

## Step 1: Install the Slack CLI

> **Note:** This step is optional. If you prefer, you can create and manage the App entirely through the web dashboard at [api.slack.com/apps](https://api.slack.com/apps).

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

**What the manifest configures:**
- **`bot_user`**: Creates the `@Prime` bot user in your workspace.
- **`socket_mode_enabled: true`**: Tells Slack to deliver events over WebSocket instead of HTTP webhooks.
- **`bot_events`**: Subscribes to `app_mention` (someone @mentions the bot) and `message.im` (someone DMs the bot).
- **`scopes`**: Grants the minimum permissions the bot needs — read mentions, read channel/thread history, write messages, and add reactions.

---

## Step 3: Collect the App-Level Token (`xapp-...`)

The App-Level Token establishes the WebSocket connection (Socket Mode) between your local machine and Slack. It **cannot** read messages or post anything — it only opens the event stream.

1. Inside your app's dashboard at [api.slack.com/apps](https://api.slack.com/apps), navigate to **Settings** > **Basic Information** (left sidebar).
2. Scroll down to the section titled **App-Level Tokens** and click **Generate Token and Scopes** (or select your existing token).
3. Set the **Token Name** to: `SocketModeToken`.
4. Click **Add Scope** and select:
   - `connections:write`
5. Click **Generate**.
6. Copy the token. It starts with **`xapp-`** (e.g., `xapp-1-A0C5...`).

---

## Step 4: Install the App & Collect Bot Token (`xoxb-...`)

The Bot Token is what gives your code the ability to act as the `@Prime` bot user — posting messages, reading threads, and adding reactions.

1. Navigate to **Settings** > **Install App** (or **OAuth & Permissions**).
2. Click the green button: **Install to Workspace** (or **Reinstall to Workspace**).
3. Review the requested permissions (`app_mentions:read`, `chat:write`, `channels:history`, etc.) and click **Allow**.
4. Once installed, copy the **Bot User OAuth Token**.
   - It begins with **`xoxb-`** (e.g., `xoxb-1219...`).

> **What just happened?** Installing the App did two things: (1) created the `@Prime` bot user in your workspace's member list, and (2) generated the `xoxb-` token that your code uses to act as that bot.

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
   # Bot User OAuth Token (acts as @Prime)
   SLACK_BOT_TOKEN=xoxb-your-actual-bot-token

   # App-Level Token (opens the WebSocket event stream)
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
1. **Token Format** — Validates that `SLACK_BOT_TOKEN` starts with `xoxb-` and `SLACK_APP_TOKEN` starts with `xapp-`.
2. **Web API Auth** — Calls `auth.test` to confirm the bot token is valid, and reports the bot's display name, User ID, and workspace name.
3. **Socket Mode WebSocket** — Opens a temporary outbound WebSocket connection to confirm that your network allows the persistent `wss://` stream.

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
   - It adds the `✅` emoji reaction upon completion.

---

## Deep Dive: Lifecycle, Code Flow & API Mechanics

This section traces the complete journey of a single event — from a user typing `@Prime help` in a Slack thread to the bot's reply appearing.

### 1. Event Ingestion (Socket Mode)

```
User types "@Prime help" in Thread
        │
        ▼
Slack Cloud detects 'app_mention' event
        │
        ▼ (pushed as JSON frame over the existing WebSocket)
        │
Your local SocketModeHandler receives the frame
        │
        ▼
Bolt framework sends acknowledgment frame back immediately
(envelope_id + empty payload — satisfies Slack's 3-second SLA)
        │
        ▼
Bolt routes the event to @app.event("app_mention") handler
```

**Key detail:** Unlike HTTP webhooks where Slack initiates a new connection for each event, Socket Mode uses a single long-lived WebSocket. Events are pushed as JSON text frames over this connection. The Bolt framework automatically handles the acknowledgment so Slack knows your app received the event.

### 2. Event Payload Structure

The `handle_app_mention` function receives a Python dictionary:

```python
{
    "type": "app_mention",
    "channel": "C0123456789",          # Channel where the mention occurred
    "user": "U012AB3CD4E",             # Who mentioned the bot
    "text": "<@U098ZY7XW6V> help",     # Raw text (includes bot's mention tag)
    "ts": "1711928400.000200",         # This message's unique timestamp
    "thread_ts": "1711928300.000100",  # Parent thread timestamp (or absent)
}
```

**Thread detection logic:**
```python
# If 'thread_ts' exists  → mention was inside an existing thread
# If 'thread_ts' is None → mention was a top-level channel message
thread_ts = event.get("thread_ts", message_ts)
```
Using `message_ts` as the fallback ensures that replies to top-level messages automatically create a new thread.

### 3. Outbound Web API Calls

After receiving the event, the code makes three separate REST API calls back to Slack (all outbound HTTPS):

| Step | Web API Method | Purpose |
| :--- | :--- | :--- |
| **Visual Feedback** | `reactions.add` | Adds 👀 emoji to show the bot is working |
| **Context Fetch** | `conversations.replies` | Retrieves up to 50 messages from the thread |
| **Reply** | `chat.postMessage` | Posts the bot's response inside the same thread |
| **Completion** | `reactions.add` | Adds ✅ emoji to signal completion |

### 4. Processing Pipeline

```python
# Thread context flows through processor.py:
reply_content = processor.process_thread_context(
    thread_messages=thread_messages,    # Full thread history (list of dicts)
    triggering_user=user_id,            # Who asked
    triggering_text=trigger_text,       # What they asked
)
```

The [`processor.py`](processor.py) module is intentionally decoupled from all Slack logic — it receives plain Python data structures and returns a plain string. This makes it trivial to swap in an LLM, script executor, or any custom automation.

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
        ],
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
