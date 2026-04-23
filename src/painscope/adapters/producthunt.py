"""Product Hunt adapter.

Uses Product Hunt GraphQL API v2 to fetch product posts and comments.
Best for: SaaS pain points, feature requests, "I wish this tool could..." signals.

Target formats:
  - Search query: "AI productivity"    → finds top products matching query
  - Product slug: "notion"             → fetches that specific product's comments

Requires PRODUCTHUNT_API_KEY + PRODUCTHUNT_API_SECRET in .env.
Get a free key at: https://www.producthunt.com/v2/oauth/applications
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

import httpx

from painscope.adapters.base import RawPost, SourceAdapter
from painscope.config import get_settings

logger = logging.getLogger(__name__)

_GQL_URL = "https://api.producthunt.com/v2/api/graphql"
_PRODUCTS_PER_SEARCH = 10
_COMMENTS_PER_POST = 50

_SEARCH_QUERY = """
query SearchPosts($topic: String!, $first: Int!) {
  posts(topic: $topic, first: $first, order: VOTES) {
    edges {
      node {
        id
        slug
        name
        tagline
        url
        votesCount
        commentsCount
        createdAt
      }
    }
  }
}
"""

_COMMENTS_QUERY = """
query PostComments($slug: String!, $first: Int!) {
  post(slug: $slug) {
    id
    name
    url
    comments(first: $first) {
      edges {
        node {
          id
          body
          createdAt
          votesCount
          user {
            username
          }
        }
      }
    }
  }
}
"""

_TOPIC_MAP: dict[str, list[str]] = {
    "ai": ["artificial-intelligence"],
    "artificial intelligence": ["artificial-intelligence"],
    "machine learning": ["artificial-intelligence"],
    "productivity": ["productivity"],
    "developer": ["developer-tools"],
    "developer tools": ["developer-tools"],
    "health": ["health-and-fitness"],
    "healthcare": ["health-and-fitness"],
    "medical": ["health-and-fitness"],
    "doctor": ["health-and-fitness"],
    "fitness": ["health-and-fitness"],
    "design": ["design-tools"],
    "marketing": ["marketing"],
    "sales": ["sales"],
    "education": ["education"],
    "finance": ["finance"],
    "crypto": ["crypto"],
    "no-code": ["no-code"],
    "saas": ["saas"],
    "social media": ["social-media"],
    "writing": ["writing"],
    "analytics": ["analytics"],
}


def _parse_dt(val: str | None) -> datetime:
    if not val:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


class ProductHuntAdapter(SourceAdapter):
    """Product Hunt posts + comments via GraphQL API v2."""

    name = "producthunt"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.producthunt_api_key:
            raise RuntimeError(
                "Product Hunt API key missing. Set PRODUCTHUNT_API_KEY in .env.\n"
                "Get a free key at: https://www.producthunt.com/v2/oauth/applications"
            )
        self._api_key = settings.producthunt_api_key
        self._api_secret = settings.producthunt_api_secret
        self._http = httpx.Client(timeout=20)
        self._bearer_token = self._fetch_token()

    def validate_target(self, target: str) -> str:
        target = target.strip()
        if not target:
            raise ValueError("Product Hunt target cannot be empty.")
        return target

    def _fetch_token(self) -> str:
        if not self._api_secret:
            return self._api_key
        try:
            resp = httpx.post(
                "https://api.producthunt.com/v2/oauth/token",
                json={
                    "client_id": self._api_key,
                    "client_secret": self._api_secret,
                    "grant_type": "client_credentials",
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
        except Exception as e:
            logger.error(f"[producthunt] OAuth2 token fetch failed: {e}")
            return self._api_key

    def _gql(self, query: str, variables: dict) -> dict:
        resp = self._http.post(
            _GQL_URL,
            json={"query": query, "variables": variables},
            headers={
                "Authorization": f"Bearer {self._bearer_token}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()

    def _query_to_topics(self, query: str) -> list[str]:
        q_lower = query.lower()
        for keyword, slugs in _TOPIC_MAP.items():
            if keyword in q_lower:
                return slugs
        return ["artificial-intelligence"]

    def _search_products(self, query: str, max_results: int) -> list[tuple[str, str, str]]:
        topics = self._query_to_topics(query)
        results = []

        for topic_slug in topics:
            try:
                data = self._gql(_SEARCH_QUERY, {"topic": topic_slug, "first": max_results})
                edges = data.get("data", {}).get("posts", {}).get("edges", [])
                for e in edges:
                    node = e.get("node", {})
                    if node.get("commentsCount", 0) > 0:
                        results.append((
                            node["slug"],
                            node["name"],
                            node.get("url") or f"https://www.producthunt.com/posts/{node['slug']}",
                        ))
            except Exception as e:
                logger.error(f"[producthunt] search failed for topic={topic_slug!r}: {e}")

        seen: set[str] = set()
        unique = []
        for item in results:
            if item[0] not in seen:
                seen.add(item[0])
                unique.append(item)
        return unique[:max_results]

    def fetch(
        self,
        target: str,
        *,
        limit: int = 500,
        language: str | None = None,
    ) -> Iterator[RawPost]:
        target = self.validate_target(target)
        count = 0

        slugs = self._search_products(target, max_results=_PRODUCTS_PER_SEARCH)
        if not slugs:
            logger.warning(f"[producthunt] No products found for {target!r}")
            return

        per_product = max(10, limit // len(slugs))

        for slug, product_name, product_url in slugs:
            if count >= limit:
                return

            for post in self._fetch_comments(
                slug=slug,
                product_name=product_name,
                product_url=product_url,
                search_query=target,
                limit=min(per_product, limit - count),
                language=language,
            ):
                yield post
                count += 1
                if count >= limit:
                    return

    def _fetch_comments(
        self,
        slug: str,
        product_name: str,
        product_url: str,
        search_query: str,
        limit: int,
        language: str | None,
    ) -> Iterator[RawPost]:
        try:
            data = self._gql(
                _COMMENTS_QUERY,
                {"slug": slug, "first": min(_COMMENTS_PER_POST, limit)},
            )
            post_data = data.get("data", {}).get("post") or {}
            edges = post_data.get("comments", {}).get("edges", [])
        except Exception as e:
            logger.warning(f"[producthunt] comments failed for slug={slug!r}: {e}")
            return

        for edge in edges:
            node = edge.get("node", {})
            body = (node.get("body") or "").strip()
            if not body:
                continue

            username = (node.get("user") or {}).get("username") or "[anon]"

            yield RawPost(
                source="producthunt",
                source_id=f"comment_{node.get('id', '')}",
                author_pseudonym=username,
                content=body,
                created_at=_parse_dt(node.get("createdAt")),
                url=product_url,
                language_hint=language,
                metadata={
                    "type": "producthunt_comment",
                    "product_slug": slug,
                    "product_name": product_name,
                    "search_query": search_query,
                    "votes": node.get("votesCount", 0),
                    "source_label": f"producthunt:{product_name}",
                },
            )
