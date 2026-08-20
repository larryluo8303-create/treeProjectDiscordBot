"""A/B testing for reply styles.

Supports multiple named style variants. Each query is randomly assigned
a variant. Satisfaction feedback is tracked per variant so the owner can
compare which style performs best.

Config via env:
- AB_TEST_ENABLED (default false)
- AB_TEST_VARIANTS (comma-separated file paths to style profiles)

Persisted to ``data/ab_results.json``.
"""

import json
import logging
import os
import random
import time
from pathlib import Path

from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

AB_TEST_ENABLED = os.getenv("AB_TEST_ENABLED", "false").lower() in ("true", "1", "yes")
AB_RESULTS_FILE = data_path(os.getenv("AB_RESULTS_FILE", "data/ab_results.json"))

# Variant definitions: list of (name, style_file_path)
_VARIANTS: list[tuple[str, str]] = []

_raw = os.getenv("AB_TEST_VARIANTS", "")
if _raw.strip():
    for entry in _raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            name, path = entry.split(":", 1)
            _VARIANTS.append((name.strip(), path.strip()))
        elif entry:
            _VARIANTS.append((Path(entry).stem, entry))


def get_variants() -> list[str]:
    """Return list of variant names."""
    return [name for name, _ in _VARIANTS]


def pick_variant() -> str | None:
    """Randomly pick a variant name. Returns None if A/B testing is disabled."""
    if not AB_TEST_ENABLED or not _VARIANTS:
        return None
    return random.choice(_VARIANTS)[0]


def get_variant_style(variant_name: str) -> str:
    """Load the style guidelines for a specific variant."""
    for name, path in _VARIANTS:
        if name == variant_name:
            try:
                return Path(path).read_text(encoding="utf-8").strip()
            except (FileNotFoundError, OSError):
                logger.warning("A/B variant style file not found: %s", path)
                return ""
    return ""


def _load_results() -> dict:
    try:
        with open(AB_RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_results(data: dict) -> None:
    atomic_json_write(AB_RESULTS_FILE, data, ensure_ascii=False, indent=2)


def record_result(variant: str, is_positive: bool) -> None:
    """Record a satisfaction result for a variant."""
    results = _load_results()
    if variant not in results:
        results[variant] = {"positive": 0, "negative": 0, "total": 0}
    results[variant]["total"] += 1
    if is_positive:
        results[variant]["positive"] += 1
    else:
        results[variant]["negative"] += 1
    _save_results(results)


def get_results() -> dict:
    """Return A/B test results per variant."""
    results = _load_results()
    summary = {}
    for variant, data in results.items():
        total = data.get("total", 0)
        positive = data.get("positive", 0)
        summary[variant] = {
            "total": total,
            "positive": positive,
            "negative": data.get("negative", 0),
            "satisfaction_rate": round(positive / total * 100, 1) if total else 0.0,
        }
    return summary
