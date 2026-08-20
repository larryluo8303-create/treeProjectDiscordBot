"""Analyze the owner's historical posts to extract style characteristics.

Run as:  python -m ingestion.analyze_style

Outputs a style profile to data/style_profile.txt that can be used
in the system prompt for more accurate style matching.
"""

import json
import logging
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bot.config import EXPORT_DIR, OWNER_USER_ID
from ingestion.preprocess import load_exports, filter_owner_messages

logger = logging.getLogger(__name__)


def _extract_ngrams(text: str, n: int) -> list[str]:
    words = re.findall(r"\b\w+\b", text.lower())
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]


def _word_count(text: str) -> int:
    """Count words/characters appropriately for CJK and non-CJK text."""
    # Count CJK characters individually, other words by spaces
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    non_cjk_words = len(re.findall(r"[a-zA-Z0-9]+", text))
    return cjk_chars + non_cjk_words


def analyze_style(export_dir: str | None = None, owner_id: str | None = None) -> str:
    """Analyze owner's posts and return a style summary string."""
    export_dir = export_dir or EXPORT_DIR
    owner_id = owner_id or str(OWNER_USER_ID)

    messages, _ = load_exports(export_dir)
    owner_msgs = filter_owner_messages(messages, owner_id)

    if not owner_msgs:
        return "No owner messages found to analyze."

    contents = [m.get("content", "").strip() for m in owner_msgs if m.get("content", "").strip()]

    # ── Metrics ──
    word_counts = [_word_count(c) for c in contents]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0
    median_words = sorted(word_counts)[len(word_counts) // 2] if word_counts else 0

    # Sentence count
    sentence_counts = [len(re.split(r"[.!?。！？]+", c)) for c in contents]
    avg_sentences = sum(sentence_counts) / len(sentence_counts) if sentence_counts else 0

    # Common bigrams / trigrams
    all_bigrams: list[str] = []
    all_trigrams: list[str] = []
    for c in contents:
        all_bigrams.extend(_extract_ngrams(c, 2))
        all_trigrams.extend(_extract_ngrams(c, 3))
    top_bigrams = Counter(all_bigrams).most_common(15)
    top_trigrams = Counter(all_trigrams).most_common(10)

    # Emoji usage
    emoji_pattern = re.compile(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        r"\U00002702-\U000027B0\U000024C2-\U0001F251]+"
    )
    all_emojis: list[str] = []
    for c in contents:
        all_emojis.extend(emoji_pattern.findall(c))
    # Discord custom emojis :name:
    discord_emojis = re.findall(r":(\w+):", " ".join(contents))
    emoji_counter = Counter(all_emojis + [f":{e}:" for e in discord_emojis])
    top_emojis = emoji_counter.most_common(10)
    emoji_pct = (len([c for c in contents if emoji_pattern.search(c) or re.search(r":\w+:", c)]) / len(contents)) * 100

    # Message length distribution
    short = sum(1 for w in word_counts if w < 20)
    medium = sum(1 for w in word_counts if 20 <= w < 60)
    long_ = sum(1 for w in word_counts if w >= 60)

    # Common opening words
    openers = Counter()
    for c in contents:
        words = c.split()
        if words:
            openers[words[0].lower()] += 1
    top_openers = openers.most_common(10)

    # ── Build summary ──
    lines = [
        f"=== Style Profile (based on {len(contents):,} messages) ===",
        "",
        f"Average response length: {avg_words:.0f} words (median {median_words})",
        f"Average sentences per message: {avg_sentences:.1f}",
        f"Length distribution: {short} short (<20w), {medium} medium (20-60w), {long_} long (60+w)",
        "",
        "Top phrases (bigrams):",
    ]
    for phrase, count in top_bigrams:
        lines.append(f"  - \"{phrase}\" ({count:,}x)")

    lines.append("")
    lines.append("Top phrases (trigrams):")
    for phrase, count in top_trigrams:
        lines.append(f"  - \"{phrase}\" ({count:,}x)")

    lines.append("")
    lines.append(f"Emoji usage: {emoji_pct:.1f}% of messages contain emojis")
    if top_emojis:
        lines.append("Top emojis: " + ", ".join(f"{e} ({c}x)" for e, c in top_emojis))

    lines.append("")
    lines.append("Common opening words:")
    for word, count in top_openers:
        lines.append(f"  - \"{word}\" ({count:,}x)")

    lines.append("")
    lines.append("Sample messages (for tone reference):")
    # Pick a few representative messages (near median length)
    sorted_by_len = sorted(contents, key=lambda c: abs(len(c.split()) - median_words))
    for sample in sorted_by_len[:5]:
        lines.append(f'  > "{sample[:200]}"')

    summary = "\n".join(lines)
    return summary


def main() -> None:
    summary = analyze_style()
    print(summary)

    out_path = Path("data/style_profile.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(summary, encoding="utf-8")
    logger.info("Style profile saved to %s", out_path)


if __name__ == "__main__":
    main()
