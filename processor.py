"""
Context Analysis and Task Processing Module for Prime Bot.

This module inspects the conversation thread context, extracts the user's intent,
and generates the appropriate update or response.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def extract_thread_summary(messages: List[Dict[str, Any]]) -> str:
    """
    Formats raw Slack thread messages into a readable conversation transcript.
    """
    formatted_lines = []
    for msg in messages:
        user = msg.get("user", "Unknown")
        text = msg.get("text", "").strip()
        formatted_lines.append(f"User [{user}]: {text}")
    return "\n".join(formatted_lines)


def process_thread_context(
    thread_messages: List[Dict[str, Any]],
    triggering_user: str,
    triggering_text: str,
) -> str:
    """
    Analyzes the thread context and generates an update.
    
    You can easily connect this to:
    - An LLM (e.g., Gemini, OpenAI, Claude, or local Ollama)
    - A local script / shell command executor
    - A database query or custom task runner
    """
    total_messages = len(thread_messages)
    logger.info("Analyzing %d messages in thread context...", total_messages)

    # 1. Clean the mention tag from the prompt if present (<@U12345678>)
    cleaned_prompt = triggering_text
    import re
    cleaned_prompt = re.sub(r"<@[A-Z0-9]+>", "", cleaned_prompt).strip()

    # 2. Extract conversation context
    transcript = extract_thread_summary(thread_messages)
    logger.debug("Thread transcript:\n%s", transcript)

    # 3. Perform work / analysis
    # [CUSTOMIZE HERE]: Insert your custom AI agent or automation logic.
    # Below is a structured response demonstrating context awareness:
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
        "_Tip: Connect `processor.py` to an LLM or local automation task for end-to-end autonomous replies._",
    ]

    return "\n".join(response_lines)
