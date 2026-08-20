"""Clarification follow-up helpers for low-confidence auto replies."""

import re


_TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")


def needs_clarification(confidence: int, max_confidence: int) -> bool:
    """Return True when confidence is low enough to ask a follow-up first."""
    return confidence <= max_confidence


def build_clarification_question(question: str) -> str:
    """Generate one concise clarification question."""
    q = (question or "").strip()
    ticker = _TICKER_RE.search(q)
    if ticker:
        return f"你问的是 `{ticker.group(0)}`。你关注的是短线(日内/1-3天)还是波段(1-4周)?"
    return "你这题我先确认下：你更关注时间框架（短线/波段）还是风险承受（保守/激进）?"


def build_clarification_reply(question: str) -> str:
    """Build the full clarification reply text."""
    return f"为避免给你模糊结论，我先确认一个关键信息：\n{build_clarification_question(question)}"
