"""
Prime Bot — Local Slack Observation & Interaction Service.

This is the core application module that connects to a Slack workspace using
**Socket Mode** (persistent outbound WebSocket over port 443) and listens for
real-time events without requiring any public HTTP endpoint, domain name, or
reverse proxy tunnel (such as ngrok).

Architecture Overview:
    ┌───────────────────┐    outbound WSS (443)    ┌─────────────────────┐
    │    Slack Cloud     │ <────────────────────── │   This Process      │
    │  (Events Engine)   │ ──────────────────────> │   (SocketModeHandler)│
    └───────────────────┘    event JSON frames     └─────────────────────┘

Supported Events:
    - ``app_mention``: Triggered when a user @mentions the bot in any channel
      or thread the bot has been invited to.
    - ``message.im``: Triggered when a user sends a direct message (DM) to the
      bot in a 1:1 conversation.

Lifecycle (per mention):
    1. Receive the ``app_mention`` event payload via WebSocket frame.
    2. Acknowledge the event within Slack's 3-second SLA (handled by Bolt).
    3. Add a 👀 (:eyes:) emoji reaction for immediate visual feedback.
    4. Fetch the full thread conversation history using ``conversations.replies``.
    5. Delegate context analysis to :mod:`processor` for AI/automation processing.
    6. Post the generated response back inside the thread via ``chat.postMessage``.
    7. Add a ✅ (:white_check_mark:) emoji reaction to signal completion.

Dependencies:
    - ``slack-bolt``: Slack's official Python framework for event-driven apps.
    - ``slack-sdk``: Low-level Slack Web API and Socket Mode client.
    - ``python-dotenv``: Loads environment variables from a ``.env`` file.

Usage:
    Ensure ``.env`` is configured with valid tokens, then run::

        $ python app.py

    See ``test_connection.py`` for a pre-flight diagnostic check.
"""

import os
import sys
import logging

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

import processor

# ---------------------------------------------------------------------------
# 1. Configuration — Load environment variables from .env
# ---------------------------------------------------------------------------
load_dotenv()

SLACK_BOT_TOKEN: str | None = os.getenv("SLACK_BOT_TOKEN")
"""Bot User OAuth Token (``xoxb-...``). Authorises the bot to call Web API
methods such as ``chat.postMessage``, ``conversations.replies``, and
``reactions.add``."""

SLACK_APP_TOKEN: str | None = os.getenv("SLACK_APP_TOKEN")
"""App-Level Token (``xapp-...``). Establishes the outbound WebSocket
connection to Slack for Socket Mode event streaming."""

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
"""Logging verbosity. Accepts standard Python log levels:
``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``."""

# ---------------------------------------------------------------------------
# 2. Logging — Structured console output with timestamps
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PrimeBot")

# ---------------------------------------------------------------------------
# 3. Startup Validation — Fail fast on misconfiguration
# ---------------------------------------------------------------------------
if not SLACK_BOT_TOKEN or not SLACK_BOT_TOKEN.startswith("xoxb-"):
    logger.error(
        "Missing or invalid SLACK_BOT_TOKEN. Must start with 'xoxb-'. "
        "Check your .env file or visit: Settings > OAuth & Permissions."
    )
    sys.exit(1)

if not SLACK_APP_TOKEN or not SLACK_APP_TOKEN.startswith("xapp-"):
    logger.error(
        "Missing or invalid SLACK_APP_TOKEN. Must start with 'xapp-'. "
        "Check your .env file or visit: Settings > Basic Information > App-Level Tokens."
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# 4. Bolt App Initialization
# ---------------------------------------------------------------------------
app = App(token=SLACK_BOT_TOKEN)


# ---------------------------------------------------------------------------
# 5. Event Handlers
# ---------------------------------------------------------------------------


@app.event("app_mention")
def handle_app_mention(event: dict, client, logger) -> None:
    """Handle ``app_mention`` events — fires when the bot is @mentioned.

    This handler orchestrates the full observation-and-response pipeline:

    1. **Visual Acknowledgement** — Adds a 👀 emoji reaction to show the
       bot is actively processing the request.
    2. **Context Extraction** — Calls the Slack Web API method
       ``conversations.replies`` to retrieve the complete thread history
       (up to 50 messages). If the mention occurred as a top-level channel
       message (not inside a thread), ``thread_ts`` falls back to the
       message's own ``ts``, so the reply still creates a tidy thread.
    3. **Processing** — Delegates the thread context to
       :func:`processor.process_thread_context`, which is the pluggable
       integration point for LLMs, shell scripts, or custom automation.
    4. **Response Posting** — Posts the processor's output back into the
       same thread via ``chat.postMessage`` with the ``thread_ts`` parameter.
    5. **Completion Signal** — Adds a ✅ emoji reaction to indicate the
       pipeline has finished.

    Args:
        event: The ``app_mention`` event payload dictionary from Slack.
            Key fields:
            - ``channel`` (str): Channel ID where the mention occurred.
            - ``ts`` (str): Timestamp of the mention message (unique ID).
            - ``thread_ts`` (str | None): Parent thread timestamp, present
              only if the mention was inside an existing reply thread.
            - ``user`` (str): User ID of the person who mentioned the bot.
            - ``text`` (str): Raw message text including ``<@BOT_ID>`` tag.
        client: The Slack ``WebClient`` instance provided by Bolt, pre-
            authenticated with ``SLACK_BOT_TOKEN``.
        logger: Scoped logger instance provided by Bolt.
    """
    channel_id: str = event.get("channel")
    message_ts: str = event.get("ts")

    # Determine the thread root:
    #   - If 'thread_ts' exists → mention was inside an existing thread.
    #   - If 'thread_ts' is absent → mention was a top-level channel message.
    #     Using message_ts as thread_ts causes the reply to create a new thread.
    thread_ts: str = event.get("thread_ts", message_ts)

    user_id: str = event.get("user")
    trigger_text: str = event.get("text", "")

    logger.info(
        "🔔 Mention received from User <%s> in Channel [%s] (Thread TS: %s)",
        user_id, channel_id, thread_ts,
    )

    # -- Step 1: Add "eyes" emoji reaction for visual feedback ---------------
    try:
        client.reactions_add(
            channel=channel_id,
            name="eyes",
            timestamp=message_ts,
        )
    except SlackApiError as e:
        # Non-fatal: the reaction is cosmetic, so we log and continue.
        logger.warning("Could not add 'eyes' reaction: %s", e.response.get("error"))

    # -- Step 2: Fetch thread context via conversations.replies --------------
    try:
        history_response = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            limit=50,  # Maximum messages to retrieve from the thread
        )
        thread_messages: list[dict] = history_response.get("messages", [])
        logger.info("Retrieved %d messages from thread context.", len(thread_messages))
    except SlackApiError as e:
        logger.error("Failed to retrieve thread history: %s", e.response.get("error"))
        # Graceful degradation: fall back to the single triggering message.
        thread_messages = [event]

    # -- Step 3: Delegate to processor for analysis / AI / automation --------
    try:
        reply_content: str = processor.process_thread_context(
            thread_messages=thread_messages,
            triggering_user=user_id,
            triggering_text=trigger_text,
        )
    except Exception as e:
        logger.exception("Error during context analysis in processor:")
        reply_content = f"⚠️ An error occurred while processing the request: `{str(e)}`"

    # -- Step 4: Post the response inside the thread -------------------------
    try:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,  # Keeps the reply nested inside the thread
            text=reply_content,
        )
        logger.info("Successfully posted response to thread %s.", thread_ts)
    except SlackApiError as e:
        logger.error("Failed to post message to Slack: %s", e.response.get("error"))

    # -- Step 5: Add completion checkmark reaction ---------------------------
    try:
        client.reactions_add(
            channel=channel_id,
            name="white_check_mark",
            timestamp=message_ts,
        )
    except SlackApiError:
        # Non-fatal: silently ignore if the reaction can't be added.
        pass


@app.event("message")
def handle_direct_messages(event: dict, client, logger) -> None:
    """Handle direct messages (1:1 DMs) sent to the bot.

    This handler only processes messages in IM (instant message) channels
    that were sent by a real user — messages originating from other bots
    (including the bot itself) are explicitly ignored to prevent infinite
    reply loops.

    Unlike ``app_mention`` events, DM messages do not require the user to
    @mention the bot — any text sent in the bot's DM window triggers this
    handler.

    Args:
        event: The ``message`` event payload dictionary from Slack.
            Key fields:
            - ``channel_type`` (str): ``"im"`` for direct messages,
              ``"channel"`` for public channels, ``"group"`` for private.
            - ``channel`` (str): Channel/DM ID.
            - ``ts`` (str): Timestamp of the message.
            - ``user`` (str): User ID who sent the message.
            - ``text`` (str): Raw message text.
            - ``bot_id`` (str | None): Present if the message was sent by a
              bot — used to filter out bot-generated messages.
        client: The Slack ``WebClient`` instance provided by Bolt.
        logger: Scoped logger instance provided by Bolt.
    """
    channel_type: str | None = event.get("channel_type")

    # Only process 1:1 direct messages from real users (not bots).
    if channel_type == "im" and not event.get("bot_id"):
        channel_id: str = event.get("channel")
        message_ts: str = event.get("ts")
        user_id: str = event.get("user")
        text: str = event.get("text", "")

        logger.info("💬 Direct message received from User <%s>: %s", user_id, text)

        # Process using the same pipeline — single-message context.
        reply_content: str = processor.process_thread_context(
            thread_messages=[event],
            triggering_user=user_id,
            triggering_text=text,
        )

        client.chat_postMessage(
            channel=channel_id,
            text=reply_content,
        )


# ---------------------------------------------------------------------------
# 6. Entry Point — Start the Socket Mode listener
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 Starting Prime Bot in Socket Mode...")
    logger.info("   Connection: Outbound WebSocket (wss://) on port 443")
    logger.info("   Tunnels:    None required (no ngrok / public webhooks)")
    logger.info("   Events:     app_mention, message.im")
    logger.info("   Processor:  processor.py")
    logger.info("=" * 60)

    # SocketModeHandler manages the WebSocket lifecycle: connection,
    # reconnection on network drops, and graceful shutdown on SIGINT/SIGTERM.
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
