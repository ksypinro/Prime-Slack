"""
Context Analysis and Task Processing Module.

This module is the **pluggable integration point** of Prime Bot. It receives
the full conversation thread context extracted from Slack and performs the
analysis, transformation, or automation task before returning a formatted
response string that gets posted back into the Slack thread.

Design Philosophy:
    The core event listener (``app.py``) handles all Slack I/O — receiving
    events, calling Web API endpoints, managing reactions. This module is
    intentionally decoupled from Slack internals so that it can be swapped
    out with any backend logic:

    - **LLM Integration**: Connect to OpenAI, Anthropic Claude, Google Gemini,
      or a locally-hosted model (e.g., Ollama) to generate intelligent replies.
    - **Shell Command Executor**: Run local scripts or CLI tools and return
      their output.
    - **Database / API Query**: Fetch data from internal systems and format
      a summary.
    - **Workflow Orchestrator**: Chain multiple steps (query → transform →
      notify) into a single automated pipeline.

Integration Example (OpenAI):
    Replace the body of :func:`process_thread_context` with::

        import openai
        conversation = "\\n".join([m.get("text", "") for m in thread_messages])
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Summarize this Slack thread."},
                {"role": "user", "content": conversation},
            ],
        )
        return response.choices[0].message.content
"""

from __future__ import annotations

import re
import logging
from typing import List, Dict, Any

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex pattern to match Slack user mention tags like <@U012AB3CD4E>
_MENTION_TAG_PATTERN: re.Pattern = re.compile(r"<@[A-Z0-9]+>")


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def extract_thread_summary(messages: List[Dict[str, Any]]) -> str:
    """Format raw Slack thread messages into a human-readable transcript.

    Each message is rendered as a single line in the format::

        User [U012AB3CD4E]: Hello, can someone review this PR?

    This transcript is useful for passing conversation history to an LLM
    or logging the thread context during debugging.

    Args:
        messages: A list of Slack message dictionaries, as returned by
            ``conversations.replies``. Each dictionary contains at minimum:
            - ``user`` (str): The Slack User ID of the message author.
            - ``text`` (str): The raw message text content.

    Returns:
        A newline-delimited string where each line represents one message
        in chronological order.

    Example:
        >>> msgs = [
        ...     {"user": "U001", "text": "Deploy is failing"},
        ...     {"user": "U002", "text": "Let me check the logs"},
        ... ]
        >>> print(extract_thread_summary(msgs))
        User [U001]: Deploy is failing
        User [U002]: Let me check the logs
    """
    formatted_lines: list[str] = []
    for msg in messages:
        user = msg.get("user", "Unknown")
        text = msg.get("text", "").strip()
        formatted_lines.append(f"User [{user}]: {text}")
    return "\n".join(formatted_lines)


def _clean_mention_tags(text: str) -> str:
    """Remove Slack user mention tags (``<@U...>``) from raw message text.

    When a user types ``@Prime please check this``, Slack transmits it as
    ``<@U098ZY7XW6V> please check this``. This helper strips those tags
    so that the downstream processor receives clean, human-readable text.

    Args:
        text: Raw Slack message text potentially containing mention tags.

    Returns:
        The cleaned text with all ``<@USER_ID>`` tags removed and
        leading/trailing whitespace stripped.
    """
    return _MENTION_TAG_PATTERN.sub("", text).strip()


# ---------------------------------------------------------------------------
# Core Processing Function
# ---------------------------------------------------------------------------

def process_thread_context(
    thread_messages: List[Dict[str, Any]],
    triggering_user: str,
    triggering_text: str,
) -> str:
    """Analyze the thread context and generate a response.

    This is the primary function called by ``app.py`` after fetching the
    thread history from Slack. It receives the full conversation context
    and the triggering user's message, then returns a formatted string
    that will be posted as a reply inside the Slack thread.

    **Customization Point**: Replace the body of this function with your
    own AI agent, script executor, or automation pipeline. The function
    signature and return type should remain the same.

    Args:
        thread_messages: List of message dictionaries from the thread,
            as returned by Slack's ``conversations.replies`` API.
            Ordered chronologically (oldest first). Each dict contains:
            - ``user`` (str): Author's Slack User ID.
            - ``text`` (str): Raw message text.
            - ``ts`` (str): Message timestamp (unique identifier).
        triggering_user: The Slack User ID of the person who @mentioned
            the bot (e.g., ``"U012AB3CD4E"``).
        triggering_text: The raw text of the triggering message, including
            the ``<@BOT_ID>`` mention tag.

    Returns:
        A formatted Slack message string (supports Slack mrkdwn syntax)
        that will be posted as a reply in the thread.
    """
    total_messages = len(thread_messages)
    logger.info("Analyzing %d messages in thread context...", total_messages)

    # 1. Clean the mention tag from the user's prompt
    cleaned_prompt = _clean_mention_tags(triggering_text)

    # 2. Extract a human-readable conversation transcript
    transcript = extract_thread_summary(thread_messages)
    logger.debug("Thread transcript:\n%s", transcript)

    # 3. Perform work / analysis
    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║  CUSTOMIZE HERE: Replace the block below with your own logic.   ║
    # ║  The current implementation returns a structured status report   ║
    # ║  demonstrating context awareness. Connect to an LLM, run a      ║
    # ║  shell command, query a database, or trigger any automation.     ║
    # ╚═══════════════════════════════════════════════════════════════════╝
    response_lines = [
        f"🤖 *Prime Bot Update* | Response to <@{triggering_user}>",
        "",
        f"*Instruction received:* \"{cleaned_prompt or 'No additional instructions provided'}\"",
        f"*Context evaluated:* Retrieved `{total_messages}` message(s) from this thread.",
        "",
        "✅ *Actions Performed:*",
        f"• Thread history parsed and analyzed ({len(transcript.splitlines())} entries).",
        "• Context inspection completed successfully.",
        "",
        "_Tip: Connect `processor.py` to an LLM or local automation task "
        "for end-to-end autonomous replies._",
    ]

    return "\n".join(response_lines)
