"""Language detection for auto-reply language matching.

Detects the language of a user's message and returns a language code.
Supports: zh (Chinese), en (English), ja (Japanese), ko (Korean).
Falls back to BOT_LANGUAGE when detection is uncertain.
"""

import re
import logging

from bot.config import BOT_LANGUAGE

logger = logging.getLogger(__name__)

# CJK Unified Ideographs + CJK Extensions
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
# Hiragana + Katakana
_JA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
# Hangul
_KO_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
# Latin alphabet words
_EN_RE = re.compile(r"[a-zA-Z]{2,}")


def detect_language(text: str) -> str:
    """Detect the primary language of *text*.

    Returns one of: 'zh', 'en', 'ja', 'ko'.
    Falls back to ``BOT_LANGUAGE`` if uncertain.
    """
    if not text or not text.strip():
        return BOT_LANGUAGE

    # Count character-class hits
    ja_count = len(_JA_RE.findall(text))
    ko_count = len(_KO_RE.findall(text))
    cjk_count = len(_CJK_RE.findall(text))
    en_words = len(_EN_RE.findall(text))

    total_chars = len(text.strip())
    if total_chars == 0:
        return BOT_LANGUAGE

    # Japanese: kana presence is a strong indicator
    if ja_count >= 2:
        return "ja"

    # Korean: hangul presence
    if ko_count >= 2:
        return "ko"

    # Chinese: CJK chars dominate
    if cjk_count >= 2:
        return "zh"

    # English: mostly latin words
    if en_words >= 2:
        return "en"

    return BOT_LANGUAGE


# Language-specific prompt suffixes telling the LLM which language to reply in
LANG_REPLY_INSTRUCTIONS: dict[str, str] = {
    "zh": "",  # default — system prompt already says 简体中文
    "en": "\n\n**Important: The user asked in English. Reply in English.**",
    "ja": "\n\n**Important: The user asked in Japanese. Reply in Japanese (日本語で回答してください).**",
    "ko": "\n\n**Important: The user asked in Korean. Reply in Korean (한국어로 답변해 주세요).**",
}


def get_reply_lang_instruction(lang: str) -> str:
    """Return a prompt instruction to reply in *lang*."""
    return LANG_REPLY_INSTRUCTIONS.get(lang, "")
