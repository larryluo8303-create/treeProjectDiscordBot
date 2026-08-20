"""Confidence scoring and routing logic."""

import logging
import re

from bot.config import CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)

# Matches the "not sure, wait for the owner" fallback (both simplified and
# traditional Chinese). Kept permissive to catch minor LLM rewordings.
_FALLBACK_PATTERN = re.compile(r"不[太]?[确確]定.*[频頻]道主|[频頻]道主.*回[答复答覆]")

# Questions asking whether there is a trade signal (buy/sell/long/short/entry).
# The bot cannot see the live chart, so these MUST always be routed to the owner
# for approval — never auto-reply, regardless of confidence or context match.
_SIGNAL_QUERY_PATTERN = re.compile(
    r"("
    # Chinese: 信号 / 信號 with question / has / any markers
    r"(有(没有|沒有|无|無)?|是否有?|有无|有無|出|出现|出現|来|來|给|給|需要?)[\s\S]{0,10}?(买|買|卖|賣|多|空|做多|做空|开仓|開倉|平仓|平倉|入场|入場|进场|進場|离场|離場|建仓|建倉|加仓|加倉|减仓|減倉|止损|止損|止盈|突破|反转|反轉)?[\s\S]{0,6}?(信号|信號|讯号|訊號)"
    r"|(信号|信號|讯号|訊號)[\s\S]{0,6}?(吗|嗎|没有|沒有|了没|了沒|了嗎|了吗|出了|出现了|出現了|来了|來了|已经|已經)"
    # Direct buy/sell/entry point questions
    r"|(可以|能|该|該|要不要|需不需要|是否)[\s\S]{0,6}?(买|買|卖|賣|做多|做空|开仓|開倉|入场|入場|进场|進場|加仓|加倉|减仓|減倉|平仓|平倉)"
    r"|(现在|現在|当前|當前|此时|此時|now)[\s\S]{0,6}?(能|可以|该|該|适合|適合|是|是否)[\s\S]{0,6}?(买|買|卖|賣|做多|做空|入场|入場|进场|進場)"
    r"|(买点|買點|卖点|賣點|买入点|買入點|卖出点|賣出點|入场点|入場點|进场点|進場點|离场点|離場點|止损点|止損點|止盈点|止盈點)"
    r")",
    re.IGNORECASE,
)


def is_signal_query(question: str) -> bool:
    """True if the question is asking about a trade signal (buy/sell/entry/exit).

    The bot has no live market data or chart access, so answers to these
    questions are unsafe to auto-post and must always be reviewed by the owner.
    """
    if not question:
        return False
    return bool(_SIGNAL_QUERY_PATTERN.search(question))


def is_fallback_answer(answer: str) -> bool:
    """True if the answer is essentially the 'I don't know, wait for owner' reply."""
    if not answer:
        return False
    stripped = answer.strip()
    # Only treat short answers as the fallback so we don't skip review on a
    # long, substantive reply that merely mentions "频道主".
    if len(stripped) > 80:
        return False
    return bool(_FALLBACK_PATTERN.search(stripped))


def parse_confidence(text: str) -> int:
    """Extract confidence score from LLM response text.

    Looks for ``CONFIDENCE: X`` at the end of the response.
    Returns a score between 1-10, defaulting to 3 if not found.
    """
    match = re.search(r"CONFIDENCE:\s*(\d+)", text, re.IGNORECASE)
    if match:
        return max(1, min(10, int(match.group(1))))
    return 3


def route_answer(
    answer: str,
    confidence: int,
    threshold: int = CONFIDENCE_THRESHOLD,
    context_count: int = 0,
    best_distance: float = 1.0,
    question: str = "",
) -> dict:
    """Decide whether to auto-reply or forward to the owner for review.

    Parameters
    ----------
    answer : str
        The generated answer text.
    confidence : int
        LLM self-assessed confidence score (1-10).
    threshold : int
        Minimum score to auto-reply.
    context_count : int
        Number of context chunks retrieved.
    best_distance : float
        Distance of the best-matching context chunk (lower = better).
    question : str
        The user's original question. Used to detect signal queries that must
        always go to owner review.

    Returns
    -------
    dict
        ``{action, answer, confidence, reason}``
    """
    action = "auto_reply"
    reason = "confidence meets threshold"

    # Signal / entry-timing questions must always be reviewed by the owner —
    # the bot cannot see the live chart, so any auto-generated "buy/sell now"
    # answer is unsafe regardless of confidence.
    if is_signal_query(question):
        action = "forward_to_owner"
        reason = "signal/entry-timing question — owner must confirm chart"
    # The "I don't know, wait for the owner" fallback is safe to post directly —
    # it's the same thing the owner would say, so skip review.
    elif is_fallback_answer(answer):
        action = "auto_reply"
        reason = "fallback answer — safe to post without review"
    # Force low confidence if no relevant context was found
    elif context_count == 0:
        action = "forward_to_owner"
        reason = "no relevant context found"
    elif best_distance > 0.95:
        # Even if LLM says confident, very distant context is suspect
        action = "forward_to_owner"
        reason = f"best context distance too high ({best_distance:.2f})"
    elif confidence < threshold:
        action = "forward_to_owner"
        reason = f"confidence {confidence} < threshold {threshold}"

    if action == "auto_reply":
        logger.info("Routing: AUTO_REPLY (confidence=%d)", confidence)
    else:
        logger.info("Routing: FORWARD_TO_OWNER — %s (confidence=%d)", reason, confidence)

    return {
        "action": action,
        "answer": answer,
        "confidence": confidence,
        "reason": reason,
    }
