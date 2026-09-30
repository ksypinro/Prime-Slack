"""
Prime Bot - Local Slack Observation & Interaction Service
Running via Slack Socket Mode (No public webhooks / ngrok needed)
"""

import os
import sys
import logging
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

import processor

# 1. Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PrimeBot")

# 2. Validate configuration
if not SLACK_BOT_TOKEN or not SLACK_BOT_TOKEN.startswith("xoxb-"):
    logger.error("Missing or invalid SLACK_BOT_TOKEN. Must start with 'xoxb-'. Check your .env file.")
    sys.exit(1)

if not SLACK_APP_TOKEN or not SLACK_APP_TOKEN.startswith("xapp-"):
    logger.error("Missing or invalid SLACK_APP_TOKEN. Must start with 'xapp-'. Check your .env file.")
    sys.exit(1)

# 3. Initialize Bolt App
app = App(token=SLACK_BOT_TOKEN)


@app.event("app_mention")
def handle_app_mention(event, client, logger):
    """
    Fires whenever @Prime is mentioned in a channel or thread.
    """
    channel_id = event.get("channel")
    message_ts = event.get("ts")
    # If the mention was in an existing thread, event has 'thread_ts'. Otherwise use 'ts' as parent.
    thread_ts = event.get("thread_ts", message_ts)
    user_id = event.get("user")
    trigger_text = event.get("text", "")

    logger.info("🔔 Mention received from User <%s> in Channel [%s] (Thread TS: %s)", user_id, channel_id, thread_ts)

    # Step 1: Add emoji reaction to signal that Prime is analyzing
    try:
        client.reactions_add(
            channel=channel_id,
            name="eyes",
            timestamp=message_ts,
        )
    except SlackApiError as e:
        logger.warning("Could not add 'eyes' reaction: %s", e.response.get("error"))

    # Step 2: Fetch thread context using conversations.replies
    try:
        history_response = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            limit=50,  # Adjust limit as needed
        )
        thread_messages = history_response.get("messages", [])
        logger.info("Retrieved %d messages from thread context.", len(thread_messages))
    except SlackApiError as e:
        logger.error("Failed to retrieve thread history: %s", e.response.get("error"))
        thread_messages = [event]  # Fallback to the single triggering message

    # Step 3: Analyze context and process the task
    try:
        reply_content = processor.process_thread_context(
            thread_messages=thread_messages,
            triggering_user=user_id,
            triggering_text=trigger_text,
        )
    except Exception as e:
        logger.exception("Error during context analysis in processor:")
        reply_content = f"⚠️ An error occurred while processing the request: `{str(e)}`"

    # Step 4: Post update back into the thread
    try:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,  # Preserves thread nesting
            text=reply_content,
        )
        logger.info("Successfully posted response to thread %s.", thread_ts)
    except SlackApiError as e:
        logger.error("Failed to post message to Slack: %s", e.response.get("error"))

    # Step 5: Mark completion with a checkmark reaction
    try:
        client.reactions_add(
            channel=channel_id,
            name="white_check_mark",
            timestamp=message_ts,
        )
    except SlackApiError:
        pass


@app.event("message")
def handle_direct_messages(event, client, logger):
    """
    Optional: Handle direct messages (1:1 DMs) sent to Prime.
    Only processes messages in IM channels that aren't bot messages.
    """
    channel_type = event.get("channel_type")
    # Only act on 1:1 direct messages (im) and ignore messages sent by bots (including itself)
    if channel_type == "im" and not event.get("bot_id"):
        channel_id = event.get("channel")
        message_ts = event.get("ts")
        user_id = event.get("user")
        text = event.get("text", "")

        logger.info("💬 Direct message received from User <%s>: %s", user_id, text)

        reply_content = processor.process_thread_context(
            thread_messages=[event],
            triggering_user=user_id,
            triggering_text=text,
        )

        client.chat_postMessage(
            channel=channel_id,
            text=reply_content,
        )


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 Starting Prime Bot in Socket Mode...")
    logger.info("No public webhooks or tunnels required.")
    logger.info("Listening for Slack events...")
    logger.info("=" * 60)

    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
