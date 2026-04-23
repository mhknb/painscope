"""Google Play Store review adapter.

Uses the `google-play-scraper` library (no API key required).
Best for: competitor analysis, feature requests, user pain points on Android apps.

Target formats:
  - Package name: "com.notion.id"       → fetches reviews directly
  - App name:     "Notion"              → searches Play Store, picks top result
  - App + lang:   "Notion:tr"           → Turkish reviews

No credentials required. Rate-limited by Google scraping policy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

from painscope.adapters.base import RawPost, SourceAdapter

logger = logging.getLogger(__name__)


def _parse_dt(val) -> datetime:
    if val is None:
        return datetime.now(timezone.utc)
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _is_package_name(target: str) -> bool:
    return "." in target and " " not in target


class GooglePlayAdapter(SourceAdapter):
    """Google Play Store reviews via google-play-scraper."""

    name = "googleplay"

    def __init__(self) -> None:
        try:
            import google_play_scraper  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "google-play-scraper not installed. "
                "Run: pip install google-play-scraper"
            )

    def validate_target(self, target: str) -> str:
        target = target.strip()
        if not target:
            raise ValueError("Google Play target cannot be empty.")
        return target

    def fetch(
        self,
        target: str,
        *,
        limit: int = 500,
        language: str | None = None,
    ) -> Iterator[RawPost]:
        from google_play_scraper import Sort, reviews

        target = self.validate_target(target)

        lang_code = language or "en"
        if ":" in target:
            parts = target.rsplit(":", 1)
            target, lang_code = parts[0].strip(), parts[1].strip()

        if _is_package_name(target):
            package = target
            app_name = target
        else:
            package, app_name = self._search_app(target, lang_code)
            if not package:
                logger.error(f"[googleplay] Could not find app: {target!r}")
                return

        logger.info(f"[googleplay] Fetching reviews for {app_name!r} ({package})")

        try:
            result, _ = reviews(
                package,
                lang=lang_code,
                country="us",
                sort=Sort.MOST_RELEVANT,
                count=limit,
            )
        except Exception as e:
            logger.error(f"[googleplay] reviews() failed for {package}: {e}")
            return

        for review in result:
            content = (review.get("content") or "").strip()
            if not content:
                continue

            yield RawPost(
                source="googleplay",
                source_id=f"review_{review.get('reviewId', '')}",
                author_pseudonym=review.get("userName") or "[anon]",
                content=content,
                created_at=_parse_dt(review.get("at")),
                url=f"https://play.google.com/store/apps/details?id={package}",
                language_hint=language,
                metadata={
                    "type": "googleplay_review",
                    "package": package,
                    "app_name": app_name,
                    "score": review.get("score", 0),
                    "thumbs_up": review.get("thumbsUpCount", 0),
                    "source_label": f"googleplay:{app_name}",
                },
            )

    def _search_app(self, name: str, lang: str) -> tuple[str | None, str]:
        try:
            from google_play_scraper import search
            results = search(name, lang=lang, country="us", n_hits=1)
            if results:
                app = results[0]
                return app["appId"], app.get("title", name)
        except Exception as e:
            logger.error(f"[googleplay] search failed for {name!r}: {e}")
        return None, name
