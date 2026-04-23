"""Xpoz-backed Reddit adapter.

Uses the Xpoz SDK (https://xpoz.ai) instead of the official Reddit API,
avoiding the need for Reddit OAuth credentials.

Requires XPOZ_API_KEY in .env. Free tier: 100k results/month.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

from painscope.adapters.base import RawPost, SourceAdapter
from painscope.config import get_settings

logger = logging.getLogger(__name__)

POSTS_PER_FETCH = 50
COMMENTS_PER_POST = 3


def _parse_dt(val) -> datetime:
    if val is None:
        return datetime.now(timezone.utc)
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        s = str(val)
        if s.isdigit():
            return datetime.fromtimestamp(int(s), tz=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


class XpozRedditAdapter(SourceAdapter):
    """Reddit adapter using Xpoz API."""

    name = "reddit"

    def __init__(self) -> None:
        from xpoz import Xpoz
        settings = get_settings()
        if not settings.xpoz_api_key:
            raise RuntimeError(
                "Xpoz API key missing. Set XPOZ_API_KEY in .env.\n"
                "Sign up at https://xpoz.ai for a free key."
            )
        self._client = Xpoz(api_key=settings.xpoz_api_key)

    def validate_target(self, target: str) -> str:
        target = target.strip().lstrip("r/")
        if not target:
            raise ValueError("Reddit target cannot be empty.")
        return target

    def fetch(
        self,
        target: str,
        *,
        limit: int = 500,
        language: str | None = None,
    ) -> Iterator[RawPost]:
        subreddit = self.validate_target(target)
        post_limit = min(limit // max(COMMENTS_PER_POST, 1), POSTS_PER_FETCH)
        broad_query = "a OR e OR i OR o OR u"

        try:
            result = self._client.reddit.search_posts(
                query=broad_query,
                subreddit=subreddit,
                limit=post_limit,
            )
            posts = result.data
        except Exception as e:
            logger.error(f"[xpoz] search_posts failed for r/{subreddit}: {e}")
            return

        for post in posts:
            if getattr(post, "over18", False):
                continue

            content = f"{post.title or ''}\n\n{getattr(post, 'selftext', '') or ''}".strip()
            if not content:
                continue

            permalink = getattr(post, "permalink", None) or f"https://reddit.com/r/{subreddit}"
            score = getattr(post, "score", None) or 0

            yield RawPost(
                source="reddit",
                source_id=f"post_{post.id}",
                author_pseudonym=getattr(post, "author_username", None) or "[deleted]",
                content=content,
                created_at=_parse_dt(
                    getattr(post, "created_at_timestamp", None)
                    or getattr(post, "created_at", None)
                    or getattr(post, "created_at_date", None)
                ),
                url=permalink,
                language_hint=language,
                metadata={
                    "type": "post",
                    "subreddit": subreddit,
                    "score": score,
                    "source_label": f"reddit:r/{subreddit}",
                },
            )

            comments_to_fetch = min(COMMENTS_PER_POST, limit)
            if comments_to_fetch > 0 and post.id:
                yield from self._fetch_comments(
                    post_id=post.id,
                    subreddit=subreddit,
                    permalink=permalink,
                    language=language,
                    limit=comments_to_fetch,
                )

    def _fetch_comments(
        self,
        post_id: str,
        subreddit: str,
        permalink: str,
        language: str | None,
        limit: int,
    ) -> Iterator[RawPost]:
        try:
            result = self._client.reddit.search_comments(
                query=post_id,
                subreddit=subreddit,
            )
            comments = result.data[:limit]
        except Exception as e:
            logger.warning(f"[xpoz] search_comments failed for {post_id}: {e}")
            return

        for comment in comments:
            body = (getattr(comment, "body", None) or "").strip()
            if not body:
                continue

            yield RawPost(
                source="reddit",
                source_id=f"comment_{getattr(comment, 'id', post_id)}",
                author_pseudonym=getattr(comment, "author_username", None) or "[deleted]",
                content=body,
                created_at=_parse_dt(
                    getattr(comment, "created_at_timestamp", None)
                    or getattr(comment, "created_at", None)
                    or getattr(comment, "created_at_date", None)
                ),
                url=permalink,
                language_hint=language,
                metadata={
                    "type": "comment",
                    "subreddit": subreddit,
                    "score": getattr(comment, "score", None) or 0,
                    "source_label": f"reddit:r/{subreddit}",
                },
            )
