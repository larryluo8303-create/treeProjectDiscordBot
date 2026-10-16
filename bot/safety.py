"""Shared safety routing for answer dispatch.

Both the message listener (bot/listener.py) and the /ask slash command
(bot/commands.py) must apply the SAME safety waterline: guardrail scanning
for high-risk content and clarification follow-ups for low-confidence
auto-replies.  Previously /ask skipped both, so the same risky answer that
would be forced to owner review in a channel could be posted directly via
/ask.
"""

import logging

from bot.clarification import build_clarification_reply, needs_clarification
from bot.confidence import is_fallback_answer
from bot.config import (
    CLARIFICATION_CONFIDENCE_MAX,
    FEATURE_CLARIFICATION_CANARY_CHANNEL_IDS,
    FEATURE_CLARIFICATION_FOLLOWUP,
    FEATURE_SAFETY_GUARDRAILS,
    FEATURE_SAFETY_GUARDRAILS_CANARY_CHANNEL_IDS,
    GUARDRAIL_DISCLAIMER,
    GUARDRAIL_MODE,
)
from bot.feature_flags import is_feature_enabled_for_channel
from bot.guardrails import detect_high_risk_signals

logger = logging.getLogger(__name__)


def apply_safety_routing(
    question: str,
    routing: dict,
    confidence: int,
    channel_id: int,
    image_urls: list | None = None,
) -> dict:
    """Apply guardrails + clarification to a routing decision (in place).

    Mutates and returns ``routing``.  ``routing`` must have ``action``,
    ``answer`` and ``reason`` keys (as produced by confidence.route_answer).
    """
    # Safety guardrails: high-risk content can be forced to owner review.
    if is_feature_enabled_for_channel(
        FEATURE_SAFETY_GUARDRAILS,
        FEATURE_SAFETY_GUARDRAILS_CANARY_CHANNEL_IDS,
        channel_id,
    ):
        risk_hits = detect_high_risk_signals(question, routing["answer"])
        if risk_hits and routing["action"] == "auto_reply":
            if GUARDRAIL_MODE == "disclaimer":
                routing["answer"] = f"{routing['answer']}\n\n{GUARDRAIL_DISCLAIMER}"
                routing["reason"] += " + guardrail disclaimer"
            else:
                routing["action"] = "forward_to_owner"
                routing["reason"] = "high-risk signal detected by guardrails"
            logger.info("Guardrail triggered (hits=%s, mode=%s)", risk_hits, GUARDRAIL_MODE)

    # Clarification follow-up: ask one clarifying question for low-confidence
    # auto replies instead of sending an ambiguous answer directly.
    # Never rewrite an honest "I don't know" fallback — replacing it with a
    # clarifying question produces nonsense (e.g. asking about 时间框架 when
    # the user asked about the weekend video). 2026-09-28 regression fix.
    if (
        routing["action"] == "auto_reply"
        and not image_urls
        and not is_fallback_answer(routing["answer"])
        and is_feature_enabled_for_channel(
            FEATURE_CLARIFICATION_FOLLOWUP,
            FEATURE_CLARIFICATION_CANARY_CHANNEL_IDS,
            channel_id,
        )
    ):
        if needs_clarification(confidence, CLARIFICATION_CONFIDENCE_MAX):
            routing["answer"] = build_clarification_reply(question)
            routing["reason"] += " + clarification follow-up"

    return routing
