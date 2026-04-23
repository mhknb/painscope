"""Preprocessing stage: language detection, PII scrubbing, dedup, filtering."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Iterable, Iterator

from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

from painscope.adapters import RawPost

logger = logging.getLogger(__name__)

# Make langdetect deterministic
DetectorFactory.seed = 0

# PII patterns to scrub (KVKK / basic privacy hygiene)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"(?:\+90[\s-]?|0)?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
TCKN_RE = re.compile(r"\b[1-9]\d{10}\b")  # 11-digit Turkish ID
CREDIT_CARD_RE = re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b")

MIN_LEN = 20
MAX_LEN = 5000


def scrub_pii(text: str) -> str:
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)
    text = TCKN_RE.sub("[id]", text)
    text = CREDIT_CARD_RE.sub("[card]", text)
    return text


def detect_language(text: str) -> str | None:
    try:
        langs = detect_langs(text[:1000])
        if langs and langs[0].prob > 0.7:
            return langs[0].lang
    except LangDetectException:
        pass
    return None


def normalize_for_dedup(text: str) -> str:
    return " ".join(text.lower().split())


def _hash(text: str) -> str:
    return hashlib.md5(normalize_for_dedup(text).encode()).hexdigest()


def preprocess(
    posts: Iterable[RawPost],
    *,
    language_filter: str | None = None,
) -> Iterator[RawPost]:
    """Apply language detection, PII scrubbing, dedup, and length filtering.

    If `language_filter` is set (e.g., "tr"), drop posts not matching.
    """
    seen_hashes: set[str] = set()
    kept = 0
    dropped_length = 0
    dropped_lang = 0
    dropped_dup = 0

    for post in posts:
        content = post.content.strip()

        # Length filter
        if len(content) < MIN_LEN:
            dropped_length += 1
            continue
        if len(content) > MAX_LEN:
            content = content[:MAX_LEN]

        # PII scrub
        content = scrub_pii(content)

        # Language detection
        lang = post.language_hint or detect_language(content)
        if language_filter and lang != language_filter:
            dropped_lang += 1
            continue

        # Dedup
        h = _hash(content)
        if h in seen_hashes:
            dropped_dup += 1
            continue
        seen_hashes.add(h)

        post.content = content
        post.language_hint = lang
        yield post
        kept += 1

    logger.info(
        f"Preprocess: kept={kept}, dropped_length={dropped_length}, "
        f"dropped_lang={dropped_lang}, dropped_dup={dropped_dup}"
    )
