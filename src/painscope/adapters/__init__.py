"""Adapter registry.

Adapters are registered here so the pipeline can discover them by name.
New adapters: add a conditional import + _REGISTRY.register() block.
"""

from __future__ import annotations

import logging

from painscope.adapters.base import RawPost, SourceAdapter
from painscope.adapters.xpoz_reddit import XpozRedditAdapter

logger = logging.getLogger(__name__)


class _AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, type[SourceAdapter]] = {}

    def register(self, cls: type[SourceAdapter]) -> None:
        self._adapters[cls.name] = cls

    def get(self, name: str) -> type[SourceAdapter] | None:
        return self._adapters.get(name)

    def available(self) -> list[str]:
        return sorted(self._adapters.keys())


REGISTRY = _AdapterRegistry()

# Always available
REGISTRY.register(XpozRedditAdapter)

# Optional: YouTube (requires YOUTUBE_API_KEY)
try:
    from painscope.adapters.youtube import YouTubeAdapter
    REGISTRY.register(YouTubeAdapter)
    logger.debug("[adapters] YouTubeAdapter registered")
except Exception as _e:
    logger.debug(f"[adapters] YouTubeAdapter unavailable: {_e}")

# Optional: Apple App Store (no key required, uses public iTunes RSS)
try:
    from painscope.adapters.appstore import AppStoreAdapter
    REGISTRY.register(AppStoreAdapter)
    logger.debug("[adapters] AppStoreAdapter registered")
except Exception as _e:
    logger.debug(f"[adapters] AppStoreAdapter unavailable: {_e}")

# Optional: Google Play (requires google-play-scraper package)
try:
    from painscope.adapters.googleplay import GooglePlayAdapter
    REGISTRY.register(GooglePlayAdapter)
    logger.debug("[adapters] GooglePlayAdapter registered")
except Exception as _e:
    logger.debug(f"[adapters] GooglePlayAdapter unavailable: {_e}")

# Optional: Product Hunt (requires PRODUCTHUNT_API_KEY + PRODUCTHUNT_API_SECRET)
try:
    from painscope.adapters.producthunt import ProductHuntAdapter
    REGISTRY.register(ProductHuntAdapter)
    logger.debug("[adapters] ProductHuntAdapter registered")
except Exception as _e:
    logger.debug(f"[adapters] ProductHuntAdapter unavailable: {_e}")


__all__ = ["REGISTRY", "RawPost", "SourceAdapter"]
