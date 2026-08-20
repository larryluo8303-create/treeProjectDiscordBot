"""High-risk answer guardrails."""

import re


_HIGH_RISK_PATTERNS = [
    re.compile(r"all\s*-?\s*in", re.IGNORECASE),
    re.compile(r"梭哈|满仓|滿倉|重仓|重倉"),
    re.compile(r"保证收益|保證收益|稳赚|穩賺|无风险|無風險"),
    re.compile(r"\d+(?:\.\d+)?%\s*(?:收益|回报|回報)"),
]


def detect_high_risk_signals(question: str, answer: str) -> list[str]:
    """Return matched high-risk reasons."""
    text = f"{question or ''}\n{answer or ''}"
    reasons: list[str] = []
    for p in _HIGH_RISK_PATTERNS:
        if p.search(text):
            reasons.append(p.pattern)
    return reasons
