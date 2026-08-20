import os
import logging
from dotenv import load_dotenv

load_dotenv()


def parse_id_list(env_key: str, default: str = "") -> list[int]:
    """Parse a comma-separated Discord snowflake list from env.

    Strips whitespace and trailing ``#`` comments so values like
    ``123, 456  # note`` still parse both IDs.
    """
    raw = os.getenv(env_key, default) or ""
    ids: list[int] = []
    for part in raw.split(","):
        token = part.split("#", 1)[0].strip()
        if token.lstrip("-").isdigit():
            ids.append(int(token))
    return ids

# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------
DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
_owner_id_raw = os.getenv("OWNER_USER_ID", "0")
try:
    OWNER_USER_ID: int = int(_owner_id_raw)
except ValueError:
    OWNER_USER_ID = 0
TARGET_CHANNEL_IDS: list[int] = parse_id_list("TARGET_CHANNEL_IDS")
EXCLUDED_CHANNEL_IDS: list[int] = parse_id_list("EXCLUDED_CHANNEL_IDS")

# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
VISION_MODEL: str = os.getenv("VISION_MODEL", "gpt-4o")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "500"))
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.5"))

# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------
CHROMADB_PATH: str = os.getenv("CHROMADB_PATH", "./chromadb_store")
CHROMADB_COLLECTION: str = "discord_posts"

# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------
RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "8"))
# Cosine distance: 0 = identical, 1 = orthogonal, 2 = opposite.
# 0.6 keeps moderately related context while filtering out clearly off-topic results.
# Raise via env var if recall feels too low; lower for stricter relevance.
RAG_MAX_DISTANCE: float = float(os.getenv("RAG_MAX_DISTANCE", "0.6"))

# ---------------------------------------------------------------------------
# Confidence routing
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD: int = int(os.getenv("CONFIDENCE_THRESHOLD", "7"))

# ---------------------------------------------------------------------------
# Thread support
# ---------------------------------------------------------------------------
THREAD_AUTO_REPLY: bool = os.getenv("THREAD_AUTO_REPLY", "true").lower() in ("1", "true", "yes")
# How many previous messages to fetch from a thread for context (on top of conversation memory)
THREAD_CONTEXT_MESSAGES: int = int(os.getenv("THREAD_CONTEXT_MESSAGES", "15"))

# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------
CONVERSATION_MEMORY_SIZE: int = int(os.getenv("CONVERSATION_MEMORY_SIZE", "10"))
CONVERSATION_MEMORY_TTL: int = int(os.getenv("CONVERSATION_MEMORY_TTL", "1800"))  # 30 minutes

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
USER_COOLDOWN_SECONDS: int = int(os.getenv("USER_COOLDOWN_SECONDS", "30"))
GLOBAL_MAX_PER_MINUTE: int = int(os.getenv("GLOBAL_MAX_PER_MINUTE", "10"))

# ---------------------------------------------------------------------------
# Response trigger mode
# ---------------------------------------------------------------------------
# 'questions'   — (default) only respond to questions / help requests / @mentions / replies-to-bot / images
# 'mention_only' — only respond when @mentioned or replied-to (most conservative)
# 'all'         — legacy behaviour: respond to every non-filtered message
RESPOND_MODE: str = os.getenv("RESPOND_MODE", "questions").lower()

# ---------------------------------------------------------------------------
# Offline backfill — on reconnect, scan for unanswered questions during downtime
# ---------------------------------------------------------------------------
OFFLINE_BACKFILL_ENABLED: bool = os.getenv("OFFLINE_BACKFILL_ENABLED", "true").lower() in ("1", "true", "yes")
# How far back to look on the very first run when no last_seen state exists.
OFFLINE_BACKFILL_LOOKBACK_HOURS: float = float(os.getenv("OFFLINE_BACKFILL_LOOKBACK_HOURS", "24"))
# Hard cap on messages fetched per channel per backfill pass.
OFFLINE_BACKFILL_MAX_PER_CHANNEL: int = int(os.getenv("OFFLINE_BACKFILL_MAX_PER_CHANNEL", "100"))
# If the owner posted any non-trivial message within this many minutes AFTER a user's question,
# treat the question as already addressed by the owner — skip auto-reply (but still learn from
# the owner's post). This covers the common case where the owner answers without using
# Discord's explicit "reply" feature. Set to 0 to disable the heuristic and only trust
# explicit replies (via message reference).
OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES: float = float(
    os.getenv("OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES", "10")
)
# Persistence file recording the last message id processed per channel.
OFFLINE_LAST_SEEN_FILE: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    os.getenv("OFFLINE_LAST_SEEN_FILE", "data/last_seen.json"),
)

# ---------------------------------------------------------------------------
# BigTreeSignal Promotion
# ---------------------------------------------------------------------------
PROMO_ENABLED: bool = os.getenv("PROMO_ENABLED", "true").lower() in ("1", "true", "yes")
PROMO_CHANNEL_IDS: list[int] = parse_id_list("PROMO_CHANNEL_IDS")
SIGNAL_PRODUCT_NAME: str = os.getenv("SIGNAL_PRODUCT_NAME", "BigTreeSignal")
SIGNAL_PRODUCT_URL: str = os.getenv("SIGNAL_PRODUCT_URL", "")
SIGNAL_CTA_TEXT: str = os.getenv("SIGNAL_CTA_TEXT", "想获取实时交易信号？了解 BigTreeSignal")
AUTO_REPLY_CTA_TEXT: str = os.getenv("AUTO_REPLY_CTA_TEXT", "想获取实时交易信号？了解 BigTreeSignal →")
CTA_FREQUENCY: int = int(os.getenv("CTA_FREQUENCY", "5"))
FREE_TRIAL_ENABLED: bool = os.getenv("FREE_TRIAL_ENABLED", "false").lower() in ("1", "true", "yes")
FREE_TRIAL_URL: str = os.getenv("FREE_TRIAL_URL", "")
WELCOME_MESSAGE: str = os.getenv(
    "WELCOME_MESSAGE",
    "欢迎加入！这里是 BigTree 的股票分析社群。",
)
TESTIMONIAL_CHANNEL_ID: int = int(os.getenv("TESTIMONIAL_CHANNEL_ID", "0"))
TESTIMONIAL_DETECTION_ENABLED: bool = os.getenv(
    "TESTIMONIAL_DETECTION_ENABLED", "true"
).lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# VIP Role Recognition
# ---------------------------------------------------------------------------
VIP_ROLE_IDS: list[int] = [
    int(rid.strip())
    for rid in os.getenv("VIP_ROLE_IDS", "").split(",")
    if rid.strip() and rid.strip().isdigit()
]

# ---------------------------------------------------------------------------
# Opt-in promo DMs (voluntary notify roles only — not ops/interest tags)
# ---------------------------------------------------------------------------
PROMO_NOTIFY_ROLE_IDS: list[int] = [
    int(rid.strip())
    for rid in os.getenv("PROMO_NOTIFY_ROLE_IDS", "").split(",")
    if rid.strip() and rid.strip().isdigit()
]
PROMO_DM_DELAY_SECONDS: float = float(os.getenv("PROMO_DM_DELAY_SECONDS", "1.2"))
PROMO_DM_MAX_RECIPIENTS: int = int(os.getenv("PROMO_DM_MAX_RECIPIENTS", "200"))

# ---------------------------------------------------------------------------
# User Satisfaction Feedback (👍/👎)
# ---------------------------------------------------------------------------
FEEDBACK_ENABLED: bool = os.getenv("FEEDBACK_ENABLED", "true").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Enhanced Welcome Flow + acquisition drip
# ---------------------------------------------------------------------------
WELCOME_FLOW_ENABLED: bool = os.getenv("WELCOME_FLOW_ENABLED", "false").lower() in ("1", "true", "yes")
# Delays from join time (seconds). Defaults: 4h value proof, 24h CTA, 72h reminder.
WELCOME_VALUE_DELAY_SECONDS: int = int(os.getenv("WELCOME_VALUE_DELAY_SECONDS", "14400"))
WELCOME_CTA_DELAY_SECONDS: int = int(os.getenv("WELCOME_CTA_DELAY_SECONDS", "86400"))
WELCOME_REMINDER_DELAY_SECONDS: int = int(os.getenv("WELCOME_REMINDER_DELAY_SECONDS", "259200"))

# ---------------------------------------------------------------------------
# Purchase-intent conversion
# ---------------------------------------------------------------------------
INTENT_CONVERT_ENABLED: bool = os.getenv("INTENT_CONVERT_ENABLED", "true").lower() in ("1", "true", "yes")
INTENT_NOTIFY_OWNER: bool = os.getenv("INTENT_NOTIFY_OWNER", "true").lower() in ("1", "true", "yes")
INTENT_LEAD_ROLE_ID: int = int(os.getenv("INTENT_LEAD_ROLE_ID", "0"))

# ---------------------------------------------------------------------------
# Invite referral
# ---------------------------------------------------------------------------
INVITE_TRACKING_ENABLED: bool = os.getenv("INVITE_TRACKING_ENABLED", "true").lower() in ("1", "true", "yes")
INVITE_REWARD_THRESHOLD: int = int(os.getenv("INVITE_REWARD_THRESHOLD", "3"))
INVITE_REWARD_ROLE_ID: int = int(os.getenv("INVITE_REWARD_ROLE_ID", "0"))

# ---------------------------------------------------------------------------
# Auto Language Detection
# ---------------------------------------------------------------------------
AUTO_LANG_DETECT: bool = os.getenv("AUTO_LANG_DETECT", "true").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Keyword Alert Monitoring
# ---------------------------------------------------------------------------
KEYWORD_ALERT_ENABLED: bool = os.getenv("KEYWORD_ALERT_ENABLED", "true").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Feature Flags + Canary Channels
# ---------------------------------------------------------------------------
FEATURE_LANG_DETECT: bool = os.getenv("FEATURE_LANG_DETECT", "true").lower() in ("1", "true", "yes")
FEATURE_LANG_DETECT_CANARY_CHANNEL_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("FEATURE_LANG_DETECT_CANARY_CHANNEL_IDS", "").split(",")
    if cid.strip() and cid.strip().isdigit()
]

FEATURE_AB_TEST: bool = os.getenv("FEATURE_AB_TEST", "false").lower() in ("1", "true", "yes")
FEATURE_AB_TEST_CANARY_CHANNEL_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("FEATURE_AB_TEST_CANARY_CHANNEL_IDS", "").split(",")
    if cid.strip() and cid.strip().isdigit()
]

# ---------------------------------------------------------------------------
# Clarification Follow-up
# ---------------------------------------------------------------------------
FEATURE_CLARIFICATION_FOLLOWUP: bool = os.getenv("FEATURE_CLARIFICATION_FOLLOWUP", "true").lower() in ("1", "true", "yes")
FEATURE_CLARIFICATION_CANARY_CHANNEL_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("FEATURE_CLARIFICATION_CANARY_CHANNEL_IDS", "").split(",")
    if cid.strip() and cid.strip().isdigit()
]
CLARIFICATION_CONFIDENCE_MAX: int = int(os.getenv("CLARIFICATION_CONFIDENCE_MAX", str(CONFIDENCE_THRESHOLD - 1)))

# ---------------------------------------------------------------------------
# Session Memory Summary
# ---------------------------------------------------------------------------
FEATURE_SESSION_SUMMARY: bool = os.getenv("FEATURE_SESSION_SUMMARY", "true").lower() in ("1", "true", "yes")
FEATURE_SESSION_SUMMARY_CANARY_CHANNEL_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("FEATURE_SESSION_SUMMARY_CANARY_CHANNEL_IDS", "").split(",")
    if cid.strip() and cid.strip().isdigit()
]
SESSION_SUMMARY_TRIGGER_MESSAGES: int = int(os.getenv("SESSION_SUMMARY_TRIGGER_MESSAGES", "12"))
SESSION_SUMMARY_KEEP_RECENT: int = int(os.getenv("SESSION_SUMMARY_KEEP_RECENT", "6"))

# ---------------------------------------------------------------------------
# Safety Guardrails
# ---------------------------------------------------------------------------
FEATURE_SAFETY_GUARDRAILS: bool = os.getenv("FEATURE_SAFETY_GUARDRAILS", "true").lower() in ("1", "true", "yes")
FEATURE_SAFETY_GUARDRAILS_CANARY_CHANNEL_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("FEATURE_SAFETY_GUARDRAILS_CANARY_CHANNEL_IDS", "").split(",")
    if cid.strip() and cid.strip().isdigit()
]
GUARDRAIL_MODE: str = os.getenv("GUARDRAIL_MODE", "force_review").lower()  # force_review|disclaimer
GUARDRAIL_DISCLAIMER: str = os.getenv(
    "GUARDRAIL_DISCLAIMER",
    "风险提示：涉及仓位/收益/点位的问题需要结合实时盘面，请谨慎判断。",
)

# ---------------------------------------------------------------------------
# Feedback-to-Ingestion Learning Loop
# ---------------------------------------------------------------------------
FEATURE_FEEDBACK_LEARNING: bool = os.getenv("FEATURE_FEEDBACK_LEARNING", "true").lower() in ("1", "true", "yes")
FEATURE_FEEDBACK_LEARNING_CANARY_CHANNEL_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("FEATURE_FEEDBACK_LEARNING_CANARY_CHANNEL_IDS", "").split(",")
    if cid.strip() and cid.strip().isdigit()
]

# ---------------------------------------------------------------------------
# SLA / Reliability Monitoring
# ---------------------------------------------------------------------------
FEATURE_SLA_MONITORING: bool = os.getenv("FEATURE_SLA_MONITORING", "true").lower() in ("1", "true", "yes")
SLA_P95_LATENCY_MS_THRESHOLD: int = int(os.getenv("SLA_P95_LATENCY_MS_THRESHOLD", "8000"))
SLA_OPENAI_ERROR_RATE_THRESHOLD: float = float(os.getenv("SLA_OPENAI_ERROR_RATE_THRESHOLD", "0.2"))
SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD: int = int(os.getenv("SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD", "20"))
SLA_SCHEDULER_MISS_SECONDS: int = int(os.getenv("SLA_SCHEDULER_MISS_SECONDS", "130"))
SLA_ALERT_COOLDOWN_SECONDS: int = int(os.getenv("SLA_ALERT_COOLDOWN_SECONDS", "900"))
SLA_ALERT_WEBHOOK_URL: str = os.getenv("SLA_ALERT_WEBHOOK_URL", "")

# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------
DIGEST_ENABLED: bool = os.getenv("DIGEST_ENABLED", "false").lower() in ("1", "true", "yes")
DIGEST_HOUR: int = int(os.getenv("DIGEST_HOUR", "22"))  # UTC hour
DIGEST_CHANNEL_ID: int = int(os.getenv("DIGEST_CHANNEL_ID", "0"))

# ---------------------------------------------------------------------------
# Jin10 Market News Feed
# ---------------------------------------------------------------------------
NEWS_FEED_ENABLED: bool = os.getenv("NEWS_FEED_ENABLED", "false").lower() in ("1", "true", "yes")
NEWS_CHANNEL_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("NEWS_CHANNEL_IDS", "").split(",")
    if cid.strip() and cid.strip().lstrip("-").isdigit()
]
NEWS_POLL_INTERVAL_SECONDS: int = int(os.getenv("NEWS_POLL_INTERVAL_SECONDS", "30"))
NEWS_IMPORTANT_ONLY: bool = os.getenv("NEWS_IMPORTANT_ONLY", "true").lower() in ("1", "true", "yes")
NEWS_BACKFILL_HOURS: int = int(os.getenv("NEWS_BACKFILL_HOURS", "24"))

# ---------------------------------------------------------------------------
# Weekly Summary — GPT-powered summary of owner messages posted on Saturday
# ---------------------------------------------------------------------------
WEEKLY_SUMMARY_ENABLED: bool = os.getenv("WEEKLY_SUMMARY_ENABLED", "false").lower() in ("1", "true", "yes")
WEEKLY_SUMMARY_CHANNELS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("WEEKLY_SUMMARY_CHANNELS", "").split(",")
    if cid.strip() and cid.strip().lstrip("-").isdigit()
]
WEEKLY_SUMMARY_DAY: int = int(os.getenv("WEEKLY_SUMMARY_DAY", "5"))  # 0=Mon, 5=Sat, 6=Sun
WEEKLY_SUMMARY_HOUR: int = int(os.getenv("WEEKLY_SUMMARY_HOUR", "14"))  # ET (UTC-4)
WEEKLY_SUMMARY_MINUTE: int = int(os.getenv("WEEKLY_SUMMARY_MINUTE", "0"))  # minute of hour
WEEKLY_SUMMARY_POST_CHANNELS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("WEEKLY_SUMMARY_POST_CHANNELS", "").split(",")
    if cid.strip() and cid.strip().lstrip("-").isdigit()
]

# ---------------------------------------------------------------------------
# Daily Summary — GPT-powered daily summary of owner messages (Mon–Fri)
# ---------------------------------------------------------------------------
DAILY_SUMMARY_ENABLED: bool = os.getenv("DAILY_SUMMARY_ENABLED", "false").lower() in ("1", "true", "yes")
DAILY_SUMMARY_CHANNELS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("DAILY_SUMMARY_CHANNELS", "").split(",")
    if cid.strip() and cid.strip().lstrip("-").isdigit()
]
DAILY_SUMMARY_DAYS: list[int] = [
    int(d.strip())
    for d in os.getenv("DAILY_SUMMARY_DAYS", "0,1,2,3,4").split(",")
    if d.strip().isdigit()
]  # 0=Mon..6=Sun, default Mon-Fri
DAILY_SUMMARY_HOUR: int = int(os.getenv("DAILY_SUMMARY_HOUR", "16"))  # ET
DAILY_SUMMARY_MINUTE: int = int(os.getenv("DAILY_SUMMARY_MINUTE", "0"))
DAILY_SUMMARY_POST_CHANNELS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("DAILY_SUMMARY_POST_CHANNELS", "").split(",")
    if cid.strip() and cid.strip().lstrip("-").isdigit()
]

# ---------------------------------------------------------------------------
# FAQ Daily Push — post FAQ to channels on a schedule
# ---------------------------------------------------------------------------
FAQ_PUSH_ENABLED: bool = os.getenv("FAQ_PUSH_ENABLED", "false").lower() in ("1", "true", "yes")
FAQ_PUSH_HOUR: int = int(os.getenv("FAQ_PUSH_HOUR", "10"))  # ET (UTC-4)
FAQ_PUSH_MINUTE: int = int(os.getenv("FAQ_PUSH_MINUTE", "0"))
FAQ_PUSH_CHANNELS: list[int] = parse_id_list("FAQ_PUSH_CHANNELS")

# ---------------------------------------------------------------------------
# Promo Monitor — auto schedule_promo when owner posts in source channel
# ---------------------------------------------------------------------------
PROMO_MONITOR_ENABLED: bool = os.getenv("PROMO_MONITOR_ENABLED", "false").lower() in ("1", "true", "yes")
PROMO_SOURCE_CHANNEL_ID: int = int(os.getenv("PROMO_SOURCE_CHANNEL_ID", "0"))
PROMO_PUSH_HOUR: int = int(os.getenv("PROMO_PUSH_HOUR", "16"))  # ET (UTC-4)
PROMO_DURATION_DAYS: int = int(os.getenv("PROMO_DURATION_DAYS", "90"))  # 3 months
PROMO_PUSH_CHANNELS: list[int] = parse_id_list("PROMO_PUSH_CHANNELS")

# ---------------------------------------------------------------------------
# YouTube Monitor — auto schedule_lesson on new video
# ---------------------------------------------------------------------------
YOUTUBE_MONITOR_ENABLED: bool = os.getenv("YOUTUBE_MONITOR_ENABLED", "false").lower() in ("1", "true", "yes")
YOUTUBE_CHANNEL_ID: str = os.getenv("YOUTUBE_CHANNEL_ID", "")
YOUTUBE_POLL_INTERVAL: int = int(os.getenv("YOUTUBE_POLL_INTERVAL", "3600"))  # seconds
YOUTUBE_CHECK_HOUR: int = int(os.getenv("YOUTUBE_CHECK_HOUR", "9"))    # ET daily check hour
YOUTUBE_CHECK_MINUTE: int = int(os.getenv("YOUTUBE_CHECK_MINUTE", "30"))  # ET daily check minute
YOUTUBE_LESSON_PUSH_HOUR: int = int(os.getenv("YOUTUBE_LESSON_PUSH_HOUR", "16"))  # ET (UTC-4)
YOUTUBE_LESSON_PUSH_CHANNELS: list[int] = parse_id_list("YOUTUBE_LESSON_PUSH_CHANNELS")
YOUTUBE_AUTO_INGEST: bool = os.getenv("YOUTUBE_AUTO_INGEST", "true").lower() in ("1", "true", "yes")
YOUTUBE_SUMMARY_CHANNELS: list[int] = parse_id_list("YOUTUBE_SUMMARY_CHANNELS")

# ---------------------------------------------------------------------------
# Auto Moderation — spam / scam / ad auto-delete
# ---------------------------------------------------------------------------
AUTO_MOD_ENABLED: bool = os.getenv("AUTO_MOD_ENABLED", "false").lower() in ("1", "true", "yes")
AUTO_MOD_LOG_CHANNEL_ID: int = int(os.getenv("AUTO_MOD_LOG_CHANNEL_ID", "0"))
AUTO_MOD_EXEMPT_ROLE_IDS: list[int] = [
    int(rid.strip())
    for rid in os.getenv("AUTO_MOD_EXEMPT_ROLE_IDS", "").split(",")
    if rid.strip() and rid.strip().isdigit()
]
AUTO_MOD_MAX_MENTIONS: int = int(os.getenv("AUTO_MOD_MAX_MENTIONS", "8"))
AUTO_MOD_MAX_LINKS: int = int(os.getenv("AUTO_MOD_MAX_LINKS", "5"))
AUTO_MOD_DUP_WINDOW: int = int(os.getenv("AUTO_MOD_DUP_WINDOW", "60"))  # seconds
AUTO_MOD_DUP_THRESHOLD: int = int(os.getenv("AUTO_MOD_DUP_THRESHOLD", "3"))  # same msg N times = spam
AUTO_MOD_BAN_WORDS_FILE: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    os.getenv("AUTO_MOD_BAN_WORDS_FILE", "data/ban_words.json"),
)
AUTO_MOD_BAN_WORDS_SIMILARITY: float = float(os.getenv("AUTO_MOD_BAN_WORDS_SIMILARITY", "0.82"))  # cosine similarity threshold
TOPIC_RESTRICTED_CHANNEL_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("TOPIC_RESTRICTED_CHANNEL_IDS", "").split(",")
    if cid.strip() and cid.strip().isdigit()
]

# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
WEBHOOK_ENABLED: bool = os.getenv("WEBHOOK_ENABLED", "false").lower() in ("1", "true", "yes")
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8081"))
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")

# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
ADMIN_ENABLED: bool = os.getenv("ADMIN_ENABLED", "false").lower() in ("1", "true", "yes")
ADMIN_PORT: int = int(os.getenv("ADMIN_PORT", "8082"))
ADMIN_SECRET: str = os.getenv("ADMIN_SECRET", "")

# ---------------------------------------------------------------------------
# API Server (FastAPI)
# ---------------------------------------------------------------------------
API_ENABLED: bool = os.getenv("API_ENABLED", "true").lower() in ("1", "true", "yes")
API_PORT: int = int(os.getenv("API_PORT", "8090"))
API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "change-me-in-production")
API_USERNAME: str = os.getenv("API_USERNAME", "admin")
API_PASSWORD: str = os.getenv("API_PASSWORD", "admin")
API_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("API_TOKEN_EXPIRE_MINUTES", "1440"))

# Public client API (no Discord required)
CLIENT_API_ENABLED: bool = os.getenv("CLIENT_API_ENABLED", "true").lower() in ("1", "true", "yes")
CLIENT_API_KEY: str = os.getenv("CLIENT_API_KEY", "")  # empty = open access
CLIENT_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("CLIENT_RATE_LIMIT_PER_MINUTE", "20"))

# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
EXPORT_DIR: str = os.getenv("EXPORT_DIR", "./data/exports")
CHUNK_MAX_TOKENS: int = int(os.getenv("CHUNK_MAX_TOKENS", "500"))
CHUNK_OVERLAP_TOKENS: int = int(os.getenv("CHUNK_OVERLAP_TOKENS", "50"))
EMBED_BATCH_SIZE: int = int(os.getenv("EMBED_BATCH_SIZE", "100"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

os.makedirs("logs", exist_ok=True)

from logging.handlers import RotatingFileHandler

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(
            "logs/bot.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)

# ---------------------------------------------------------------------------
# Language / i18n
# ---------------------------------------------------------------------------
BOT_LANGUAGE: str = os.getenv("BOT_LANGUAGE", "zh")

LOCALE: dict[str, dict[str, str]] = {
    "zh": {
        "rate_limited_user": "\u8bf7\u7a0d\u540e\u518d\u8bd5\uff0c\u7528\u6237\u901f\u7387\u9650\u5236\u4e2d\u3002",
        "rate_limited_global": "\u8bf7\u7a0d\u540e\u518d\u8bd5\uff0c\u5168\u5c40\u901f\u7387\u9650\u5236\u4e2d\u3002",
        "no_answer": "\u62b1\u6b49\uff0c\u76ee\u524d\u65e0\u6cd5\u751f\u6210\u56de\u590d\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002",
        "unsure": "\u8fd9\u4e2a\u6211\u4e0d\u592a\u786e\u5b9a\uff0c\u7b49\u9891\u9053\u4e3b\u6765\u56de\u7b54",
        "owner_only": "\u53ea\u6709\u9891\u9053\u4e3b\u53ef\u4ee5\u4f7f\u7528\u6b64\u547d\u4ee4\u3002",
        "channel_disabled": "\u6b64\u9891\u9053\u672a\u5f00\u542f\u95ee\u7b54\u529f\u80fd\u3002",
        "promo_disabled": "\u63a8\u5e7f\u529f\u80fd\u5df2\u5173\u95ed\u3002",
        "promo_channel_disabled": "\u6b64\u9891\u9053\u672a\u5f00\u542f\u63a8\u5e7f\u529f\u80fd\u3002",
        "no_testimonials": "\u6682\u65e0\u7528\u6237\u89c1\u8bc1\u3002",
        "review_rejected": "\u274c **Rejected. No reply sent.**",
        "review_approved": "\u2705 **Approved & sent.**",
        "already_handled": "Already handled.",
        "conversation_user": "\u6210\u5458",
        "conversation_bot": "\u4f60(\u9891\u9053\u4e3b)",
        "conversation_header": "\u4ee5\u4e0b\u662f\u8be5\u9891\u9053\u6700\u8fd1\u7684\u5bf9\u8bdd\u8bb0\u5f55\uff1a\n",
    },
    "en": {
        "rate_limited_user": "Please wait — user rate limit in effect.",
        "rate_limited_global": "Please wait — global rate limit in effect.",
        "no_answer": "Sorry, I can't generate a reply right now. Please try again later.",
        "unsure": "I'm not sure about this, let me defer to the channel owner.",
        "owner_only": "Only the channel owner can use this command.",
        "channel_disabled": "Q&A is not enabled in this channel.",
        "promo_disabled": "Promotion features are disabled.",
        "promo_channel_disabled": "Promotion is not enabled in this channel.",
        "no_testimonials": "No testimonials yet.",
        "review_rejected": "\u274c **Rejected. No reply sent.**",
        "review_approved": "\u2705 **Approved & sent.**",
        "already_handled": "Already handled.",
        "conversation_user": "Member",
        "conversation_bot": "You (Owner)",
        "conversation_header": "Recent conversation history:\n",
    },
}


def get_locale(key: str) -> str:
    """Return the localized string for *key* in the active BOT_LANGUAGE."""
    lang = BOT_LANGUAGE if BOT_LANGUAGE in LOCALE else "zh"
    return LOCALE[lang].get(key, LOCALE["zh"].get(key, key))


# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_TEMPLATE: str = """你是一个AI助手，负责完全模仿频道主的说话风格来回答问题。
你在一个使用简体中文的Discord股票/投资讨论频道中回答成员的问题。

语言要求：必须使用简体中文回复。

风格指南：
{style_guidelines}

规则：
1. 只根据提供的历史帖子内容来回答，不要凭空捏造。
2. 如果历史内容不足以自信地回答，简短说明即可。
3. 不要编造投资建议，只转述历史帖子中出现过的观点。
4. 严格匹配示例帖子的语气、长度和用词习惯。
5. 除非原始风格包含免责声明，否则不要添加"以上不构成投资建议"等套话。
6. 回复要简洁自然，就像在Discord里直接打字一样。
7. 【点位脱敏 - 但要做完整分析】欢迎做完整的技术分析：趋势判断、形态识别（HH/HL/LL/LH、背驰、中枢、三个买点）、指标解读（MACD/RSI/EMA 等）、交易逻辑、仓位和止损原则。全部详细说，这才是干货。唯一严禁的是：不得在回答中提及任何具体价格数字、点位区间或目标价（包括 2 位数、如 "86、92、178"，也包括 3-5 位数、如 "3912、3950、250.5"）。原因：点位有时效性，过去的数字对当前无参考价值。必须用相对描述代替具体数字：
   - "支撑位 3900" → "前期低点支撑 / 近期支撑区域 / 均线附近支撑"
   - "突破 3950" → "突破前期高点 / 突破关键压力"
   - "目标 250" → "目标看前高 / 目标上方压力区"
   - "止损 3850" → "跌破关键位止损 / 结构走坏止损"
   - "3900-3950 区间" → "前期振荡区 / 压力区域"
   - "86 附近减过" → "之前买信号附近减过 / 前期买点附近减过"
   - "之前提到的 86 附近" → "之前提到的那个买信号附近 / 之前的仓位附近"
   - "EMA13 在 250" → "价格靠近 EMA13"
   指标参数本身可以提（如 EMA13、RSI 70、MA200），那是指标设置不是价格。时间周期也可以提（如 5min、1h、4h、日线）。仓位百分比也可以提（90%仓位、5% 重仓）。仅禁 "价格本身的具体数字"。如果用户专门追问具体点位数字，回复 "具体点位需要根据当前实时行情判断，我只能分享分析方法和思路"。
8. 【回复质量要求】每句话都要有信息量，直接给出干货。严禁以下口水话模式：
   - 禁止用"好问题"、"这个问题很好"等开头
   - 禁止用"简单来说"、"其实就是"等无意义过渡
   - 禁止重复用户的问题（用户已经知道自己问了什么）
   - 禁止在结尾加"希望对你有帮助"、"祝你交易顺利"等客套话
   - 禁止说"根据我的经验"、"我认为"等前缀，直接给结论
   - 回复开头直接切入要点，不要铺垫
9. 【不确定就不回答】如果历史帖子中没有足够相关内容来给出有实质意义的回答，不要硬凑、不要打太极、不要绕弯子。直接回复"这个我不太确定，等频道主来回答"即可，然后给低置信度分数（1-3）。宁可不答，也不要给出模棱两可、没有信息量的废话。

在回复的最后，另起一行，严格输出：
CONFIDENCE: X
其中X是1到10的数字。严格按以下评分标准，不要漂亮化打分：
- 1-3：检索内容与问题几乎不相关，或你的回答是"不确定/等频道主回答"。必须转人工审查。
- 4-6：历史内容只能部分回答问题，或你需要从不同帖子拼凑推断。不够自信。
- 7-8：检索内容明确覆盖问题，你的回答几乎是在重述频道主说过的话。可以自动回复。
- 9-10：检索到的帖子几乎完全回答了这个问题，你几乎是原话转述。罕见，不要轻易给。
默认偏保守：如果犹豫该给 6 还是 7，给 6。打低不会错。"""

DEFAULT_STYLE_GUIDELINES: str = """- 语气随意但专业，像在和朋友聊股票。
- 回复简洁，通常1-3句话，每句必须有实质内容。
- 有明确观点时直接表达，不绕弯子。
- 使用历史帖子中出现的相同词汇和表达方式。
- 适当使用中文股市常用词汇（如：涨停、跌停、主力、散户、建仓、出货等）。
- 优先输出方法论、具体指标用法、操作逻辑等干货内容。
- 模仿频道主的简洁风格：直接给结论和做法，不做多余解释。
- 不确定的事情不要硬答，不打太极不绕弯子。"""

USER_PROMPT_TEMPLATE: str = """以下是我过去在频道中发过的相关帖子和回答：

{context}

{conversation_history}一位成员提问："{question}"

请根据我上面的历史帖子，用我的风格来回答这个问题。如果对话记录中有上下文相关信息，请结合来回答。"""
