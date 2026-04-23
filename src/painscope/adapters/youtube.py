"""YouTube Data API v3 adapter.

Fetches comments from videos matching a search query (or a specific video ID).
Best for: "what do people complain about in AI tutorial videos?",
          "what questions do healthcare professionals ask about AI tools?"

Target formats:
  - Search query: "notion tutorial" → finds top videos, fetches their comments
  - Video ID:     "dQw4w9WgXcQ"    → fetches comments for that specific video

Requires YOUTUBE_API_KEY in .env (Google Cloud Console → YouTube Data API v3).
Free quota: 10,000 units/day. This adapter uses ~3 units per video fetched.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

import httpx

from painscope.adapters.base import RawPost, SourceAdapter
from painscope.config import get_settings

logger = logging.getLogger(__name__)

_BASE = "https://www.googleapis.com/youtube/v3"
_VIDEOS_PER_SEARCH = 10
_COMMENTS_PER_VIDEO = 50


def _parse_dt(iso: str | None) -> datetime:
    if not iso:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _is_video_id(target: str) -> bool:
    return len(target) == 11 and all(c.isalnum() or c in "-_" for c in target)


class YouTubeAdapter(SourceAdapter):
    """Fetch YouTube video comments via YouTube Data API v3."""

    name = "youtube"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.youtube_api_key:
            raise RuntimeError(
                "YouTube API key missing. Set YOUTUBE_API_KEY in .env.\n"
                "Get one at: https://console.cloud.google.com → YouTube Data API v3"
            )
        self._key = settings.youtube_api_key
        self._http = httpx.Client(timeout=15)

    def validate_target(self, target: str) -> str:
        target = target.strip()
        if not target:
            raise ValueError("YouTube target cannot be empty.")
        return target

    def fetch(
        self,
        target: str,
        *,
        limit: int = 500,
        language: str | None = None,
    ) -> Iterator[RawPost]:
        target = self.validate_target(target)

        if _is_video_id(target):
            video_ids = [target]
        else:
            video_ids = self._search_videos(target, max_results=_VIDEOS_PER_SEARCH)

        if not video_ids:
            logger.warning(f"[youtube] No videos found for target={target!r}")
            return

        count = 0
        per_video = max(1, limit // len(video_ids))

        for video_id in video_ids:
            if count >= limit:
                return
            for post in self._fetch_comments(
                video_id=video_id,
                search_query=target,
                limit=min(per_video, limit - count),
                language=language,
            ):
                yield post
                count += 1
                if count >= limit:
                    return

    def _search_videos(self, query: str, max_results: int = 10) -> list[str]:
        try:
            resp = self._http.get(
                f"{_BASE}/search",
                params={
                    "part": "id",
                    "q": query,
                    "type": "video",
                    "maxResults": max_results,
                    "order": "relevance",
                    "key": self._key,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            return [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]
        except Exception as e:
            logger.error(f"[youtube] search failed for {query!r}: {e}")
            return []

    def _fetch_comments(
        self,
        video_id: str,
        search_query: str,
        limit: int,
        language: str | None,
    ) -> Iterator[RawPost]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        fetched = 0
        page_token: str | None = None

        while fetched < limit:
            params: dict = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": min(_COMMENTS_PER_VIDEO, limit - fetched),
                "order": "relevance",
                "key": self._key,
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                resp = self._http.get(f"{_BASE}/commentThreads", params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"[youtube] commentThreads failed for {video_id}: {e}")
                return

            for item in data.get("items", []):
                snippet = (
                    item.get("snippet", {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                )
                text = (snippet.get("textDisplay") or snippet.get("textOriginal") or "").strip()
                if not text:
                    continue

                yield RawPost(
                    source="youtube",
                    source_id=f"comment_{item['id']}",
                    author_pseudonym=snippet.get("authorDisplayName") or "[anon]",
                    content=text,
                    created_at=_parse_dt(snippet.get("publishedAt")),
                    url=url,
                    language_hint=language,
                    metadata={
                        "type": "youtube_comment",
                        "video_id": video_id,
                        "search_query": search_query,
                        "like_count": snippet.get("likeCount", 0),
                        "source_label": f"youtube:{search_query}",
                    },
                )
                fetched += 1
                if fetched >= limit:
                    return

            page_token = data.get("nextPageToken")
            if not page_token:
                break
