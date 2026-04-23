"""Reddit adapter using official PRAW library.

Reddit's Data API is the legal source. Free tier: 100 req/min OAuth,
~10k/month. We cache aggressively upstream (in storage layer).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

import praw

from painscope.adapters.base import RawPost, SourceAdapter
from painscope.config import get_settings

logger = logging.getLogger(__name__)


class RedditAdapter(SourceAdapter):
    name = "reddit"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.reddit_client_id or not settings.reddit_client_secret:
            raise RuntimeError(
                "Reddit credentials missing. Set REDDIT_CLIENT_ID and "
                "REDDIT_CLIENT_SECRET in your .env file. Create an app at "
                "https://www.reddit.com/prefs/apps (type: script)."
            )
        self.reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )
        self.reddit.read_only = True

    def validate_target(self, target: str) -> str:
        # Accept "r/Turkey", "/r/Turkey", or plain "Turkey"
        cleaned = target.strip().lstrip("/")
        if cleaned.lower().startswith("r/"):
            cleaned = cleaned[2:]
        if not cleaned or "/" in cleaned:
            raise ValueError(f"Invalid subreddit: {target!r}")
        return cleaned

    def fetch(
        self,
        target: str,
        *,
        limit: int = 500,
        language: str | None = None,
    ) -> Iterator[RawPost]:
        subreddit_name = self.validate_target(target)
        subreddit = self.reddit.subreddit(subreddit_name)

        logger.info(f"Fetching up to {limit} submissions from r/{subreddit_name}")

        count = 0
        # Grab top submissions from the past month — good balance of
        # recency and signal strength. You can switch to .new() or .hot().
        for submission in subreddit.top(time_filter="month", limit=limit):
            if submission.stickied or submission.over_18:
                continue

            # Yield the submission itself
            yield RawPost(
                source="reddit",
                source_id=submission.id,
                author_pseudonym=str(submission.author) if submission.author else "[deleted]",
                content=f"{submission.title}\n\n{submission.selftext}".strip(),
                created_at=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
                url=f"https://reddit.com{submission.permalink}",
                language_hint=language,
                metadata={
                    "type": "submission",
                    "score": submission.score,
                    "num_comments": submission.num_comments,
                    "subreddit": subreddit_name,
                },
            )
            count += 1
            if count >= limit:
                return

            # Also yield top-level comments for richer pain-point signal
            submission.comments.replace_more(limit=0)
            for comment in submission.comments[:10]:
                if count >= limit:
                    return
                if not hasattr(comment, "body") or comment.body in ("[deleted]", "[removed]"):
                    continue
                yield RawPost(
                    source="reddit",
                    source_id=comment.id,
                    author_pseudonym=str(comment.author) if comment.author else "[deleted]",
                    content=comment.body,
                    created_at=datetime.fromtimestamp(comment.created_utc, tz=timezone.utc),
                    url=f"https://reddit.com{comment.permalink}",
                    language_hint=language,
                    metadata={
                        "type": "comment",
                        "score": comment.score,
                        "parent_id": submission.id,
                        "subreddit": subreddit_name,
                    },
                )
                count += 1
