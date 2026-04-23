"""Base contract for all data source adapters.

Every legal data source (Reddit, YouTube, HN, App Store, Stack Exchange,
GitHub) implements this interface. New sources drop in without changing
the pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator


@dataclass(slots=True)
class RawPost:
    """A single post/comment/review fetched from any source.

    The shape is unified across all adapters so the downstream pipeline
    is source-agnostic.
    """

    source: str  # "reddit" | "youtube" | "hackernews" | "appstore" | ...
    source_id: str  # stable unique id within the source
    author_pseudonym: str  # username or pseudonym; never used as PII
    content: str  # the text of the post/comment/review
    created_at: datetime
    url: str  # link back to the original
    language_hint: str | None = None  # "tr" | "en" | None
    metadata: dict = field(default_factory=dict)  # source-specific extras

    def as_doc_for_embedding(self) -> str:
        """Return the text to embed. Subclasses can override if needed."""
        return self.content.strip()


class SourceAdapter(ABC):
    """Abstract base for all source adapters."""

    name: str  # shortname like "reddit", "youtube"

    @abstractmethod
    def fetch(
        self,
        target: str,
        *,
        limit: int = 500,
        language: str | None = None,
    ) -> Iterator[RawPost]:
        """Fetch up to `limit` posts for the given `target`.

        `target` format is source-specific:
          - reddit: "r/Turkey" or "Turkey"
          - youtube: channel_id or video_id
          - appstore: app_id (numeric)
          - hackernews: keyword query
          - stackexchange: tag name
          - github: "owner/repo"
        """
        ...

    @abstractmethod
    def validate_target(self, target: str) -> str:
        """Normalize and validate the target string. Raise ValueError if invalid."""
        ...
