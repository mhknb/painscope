"""Apple App Store review adapter.

Uses Apple's public iTunes RSS + Search API (no auth required).
Best for: competitor analysis, feature requests, user pain points.

Target formats:
  - App name:  "Notion"          → searches App Store, picks top result
  - App ID:    "1464122853"      → fetches reviews directly
  - App + country: "Notion:tr"   → Turkish App Store reviews

Free, no API key needed. Returns up to 500 reviews per app (10 pages × 50).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

import httpx

from painscope.adapters.base import RawPost, SourceAdapter

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://itunes.apple.com/search"
_REVIEWS_PAGE_URL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortBy=mostRecent/json"
_MAX_PAGES = 10


def _parse_dt(val: str | None) -> datetime:
    if not val:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


class AppStoreAdapter(SourceAdapter):
    """Apple App Store reviews via iTunes RSS API."""

    name = "appstore"

    def __init__(self) -> None:
        self._http = httpx.Client(timeout=15, headers={"User-Agent": "painscope/0.1"})

    def validate_target(self, target: str) -> str:
        target = target.strip()
        if not target:
            raise ValueError("App Store target cannot be empty.")
        return target

    def fetch(
        self,
        target: str,
        *,
        limit: int = 500,
        language: str | None = None,
    ) -> Iterator[RawPost]:
        target = self.validate_target(target)

        country = "us"
        if ":" in target:
            parts = target.rsplit(":", 1)
            target, country = parts[0].strip(), parts[1].strip().lower()

        if target.isdigit():
            app_id = target
            app_name = f"app_{app_id}"
        else:
            app_id, app_name = self._search_app(target, country)
            if not app_id:
                logger.error(f"[appstore] Could not find app: {target!r}")
                return

        logger.info(f"[appstore] Fetching reviews for {app_name!r} (id={app_id}, country={country})")
        yield from self._fetch_reviews(app_id, app_name, country, limit, language)

    def _search_app(self, name: str, country: str) -> tuple[str | None, str]:
        try:
            resp = self._http.get(
                _SEARCH_URL,
                params={"term": name, "country": country, "entity": "software", "limit": 1},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                app = results[0]
                return str(app["trackId"]), app.get("trackName", name)
        except Exception as e:
            logger.error(f"[appstore] search failed for {name!r}: {e}")
        return None, name

    def _fetch_reviews(
        self,
        app_id: str,
        app_name: str,
        country: str,
        limit: int,
        language: str | None,
    ) -> Iterator[RawPost]:
        fetched = 0

        for page in range(1, _MAX_PAGES + 1):
            if fetched >= limit:
                return

            url = _REVIEWS_PAGE_URL.format(country=country, page=page, app_id=app_id)
            try:
                resp = self._http.get(url)
                resp.raise_for_status()
                feed = resp.json().get("feed", {})
                entries = feed.get("entry", [])
            except Exception as e:
                logger.warning(f"[appstore] page {page} failed for {app_id}: {e}")
                break

            if page == 1 and entries:
                entries = entries[1:]  # first entry is app metadata

            if not entries:
                break

            for entry in entries:
                if fetched >= limit:
                    return

                title = entry.get("title", {}).get("label", "")
                body = entry.get("content", {}).get("label", "")
                if not body and not title:
                    continue

                content = f"{title}\n\n{body}".strip() if title else body.strip()
                rating = entry.get("im:rating", {}).get("label", "")
                author = entry.get("author", {}).get("name", {}).get("label", "[anon]")
                review_id = entry.get("id", {}).get("label", f"{app_id}_{fetched}")
                updated = entry.get("updated", {}).get("label")

                yield RawPost(
                    source="appstore",
                    source_id=f"review_{review_id}",
                    author_pseudonym=author,
                    content=content,
                    created_at=_parse_dt(updated),
                    url=f"https://apps.apple.com/{country}/app/id{app_id}",
                    language_hint=language,
                    metadata={
                        "type": "appstore_review",
                        "app_id": app_id,
                        "app_name": app_name,
                        "rating": rating,
                        "country": country,
                        "source_label": f"appstore:{app_name}",
                    },
                )
                fetched += 1
