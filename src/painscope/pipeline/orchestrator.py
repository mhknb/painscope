"""End-to-end pipeline orchestrator.

Ties together: fetch → preprocess → embed → cluster → summarize → rank.
This is what both the CLI and the MCP server call.
"""

from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np

from painscope.adapters import RawPost, get_adapter
from painscope.pipeline.cluster import cluster as cluster_embeddings
from painscope.pipeline.embed import embed_texts
from painscope.pipeline.preprocess import preprocess
from painscope.pipeline.summarize import ContentIdea, PainPoint, summarize_cluster

logger = logging.getLogger(__name__)

ScanType = Literal["pain_points", "content_ideas"]


@dataclass
class ScanResult:
    scan_id: str
    source: str
    target: str
    scan_type: ScanType
    language: str
    started_at: datetime
    completed_at: datetime
    model_used: str | None
    total_posts_fetched: int
    total_posts_used: int
    num_clusters: int
    insights: list[dict] = field(default_factory=list)  # serialized PainPoint/ContentIdea
    duration_seconds: float = 0.0
    # Multi-source: populated by run_topic_scan
    sources: list[dict] = field(default_factory=list)


def _source_distribution(cluster_posts: list[RawPost]) -> dict[str, int]:
    """Count posts per source label in a cluster.

    Each post carries a 'source_label' in its metadata (set at fetch time).
    For single-source scans the dict has one key; multi-source has many.
    Cross-source confirmation: if the same pain appears in 3 different
    communities, the distribution shows it clearly.
    """
    dist: dict[str, int] = {}
    for p in cluster_posts:
        label = p.metadata.get("source_label", p.metadata.get("subreddit", p.source))
        dist[label] = dist.get(label, 0) + 1
    return dict(sorted(dist.items(), key=lambda x: -x[1]))


def _recency_decay(posts: list[RawPost], half_life_days: float = 30.0) -> float:
    """Average recency weight for a cluster. Newer = higher."""
    if not posts:
        return 0.0
    now = datetime.now(timezone.utc)
    weights = []
    for p in posts:
        age_days = max(0, (now - p.created_at).total_seconds() / 86400)
        weights.append(math.pow(0.5, age_days / half_life_days))
    return sum(weights) / len(weights)


def _rank_insights(
    insights: list[tuple[dict, list[RawPost]]]
) -> list[dict]:
    """Rank insights: cluster_size * severity * recency.

    Each element of `insights` is (insight_dict, cluster_posts).
    """
    scored = []
    for insight_dict, posts in insights:
        size = len(posts)
        severity = insight_dict.get("severity", 3)  # content_ideas has no severity
        recency = _recency_decay(posts)
        score = size * severity * (0.5 + recency)  # floor recency at 0.5 so old clusters aren't zeroed
        insight_dict["_score"] = round(score, 2)
        insight_dict["_cluster_size"] = size
        scored.append(insight_dict)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored


def run_scan(
    source: str,
    target: str,
    *,
    scan_type: ScanType = "pain_points",
    language: str = "tr",
    limit: int = 500,
    top_n: int = 15,
    model: str | None = None,
) -> ScanResult:
    """Run a full scan end-to-end.

    Returns a ScanResult. Caller is responsible for persisting / rendering.
    """
    started = time.time()
    started_at = datetime.now(timezone.utc)
    scan_id = started_at.strftime("%Y%m%d-%H%M%S") + f"-{source}-{target.replace('/', '_')}"

    # 1. Fetch
    logger.info(f"[{scan_id}] Fetching from {source}:{target}")
    adapter = get_adapter(source)
    raw_posts = list(adapter.fetch(target, limit=limit, language=language))
    logger.info(f"[{scan_id}] Fetched {len(raw_posts)} raw posts")

    # 2. Preprocess
    processed = list(preprocess(raw_posts, language_filter=language))
    logger.info(f"[{scan_id}] After preprocess: {len(processed)} posts")

    if len(processed) < 10:
        logger.warning(f"[{scan_id}] Too few posts after preprocessing; returning empty result.")
        return ScanResult(
            scan_id=scan_id,
            source=source,
            target=target,
            scan_type=scan_type,
            language=language,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            model_used=model,
            total_posts_fetched=len(raw_posts),
            total_posts_used=len(processed),
            num_clusters=0,
            insights=[],
            duration_seconds=time.time() - started,
        )

    # 3. Embed
    texts = [p.as_doc_for_embedding() for p in processed]
    embeddings = embed_texts(texts)

    # 4. Cluster
    labels = cluster_embeddings(embeddings)
    unique_clusters = sorted(set(labels) - {-1})
    logger.info(f"[{scan_id}] Found {len(unique_clusters)} clusters")

    # 5. Summarize each cluster
    insights_with_posts: list[tuple[dict, list[RawPost]]] = []
    for cluster_id in unique_clusters:
        cluster_posts = [p for p, lbl in zip(processed, labels) if lbl == cluster_id]
        try:
            result = summarize_cluster(
                cluster_posts, scan_type=scan_type, language=language, model=model
            )
            insight_dict = result.model_dump()
            insight_dict["source_distribution"] = _source_distribution(cluster_posts)
            insights_with_posts.append((insight_dict, cluster_posts))
        except Exception as e:
            logger.error(f"[{scan_id}] Failed to summarize cluster {cluster_id}: {e}")

    # 6. Rank + trim
    ranked = _rank_insights(insights_with_posts)[:top_n]

    completed_at = datetime.now(timezone.utc)
    return ScanResult(
        scan_id=scan_id,
        source=source,
        target=target,
        scan_type=scan_type,
        language=language,
        started_at=started_at,
        completed_at=completed_at,
        model_used=model,
        total_posts_fetched=len(raw_posts),
        total_posts_used=len(processed),
        num_clusters=len(unique_clusters),
        insights=ranked,
        duration_seconds=time.time() - started,
    )


# ── Multi-source: run_topic_scan ─────────────────────────────────────────────

def _fetch_one_source(
    source_cfg: Any,
    *,
    default_language: str,
    default_limit: int,
) -> tuple[list[RawPost], dict]:
    """Fetch a single source. Returns (posts, stats_dict)."""
    from painscope.topics import SourceConfig  # local import to avoid circular

    adapter = get_adapter(source_cfg.type)
    lang = source_cfg.language or default_language
    limit = source_cfg.limit or default_limit
    label = source_cfg.resolved_label

    posts = list(adapter.fetch(source_cfg.target, limit=limit, language=lang))

    # Tag every post with its source label so clustering output can
    # show cross-source confirmation
    for p in posts:
        p.metadata["source_label"] = label

    stats = {
        "type": source_cfg.type,
        "target": source_cfg.target,
        "label": label,
        "posts_fetched": len(posts),
    }
    return posts, stats


def run_topic_scan(config: Any) -> ScanResult:
    """Run a multi-source scan from a TopicConfig.

    Fetches all sources in parallel (ThreadPoolExecutor), merges the post
    pool, then runs the unified embedding → clustering → summarization
    pipeline on the combined data.

    Cross-source confirmation is surfaced in each insight's
    `source_distribution` dict — e.g. {"r/Turkey": 14, "r/KGBTR": 6}.
    """
    started = time.time()
    started_at = datetime.now(timezone.utc)
    safe_name = config.name.replace(" ", "_").replace("/", "_")[:40]
    scan_id = started_at.strftime("%Y%m%d-%H%M%S") + f"-topic-{safe_name}"

    logger.info(f"[{scan_id}] Topic scan: {config.name!r} — {len(config.sources)} sources")

    # 1. Parallel fetch
    all_posts: list[RawPost] = []
    source_stats: list[dict] = []
    max_workers = min(len(config.sources), 5)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _fetch_one_source,
                src,
                default_language=config.language,
                default_limit=config.limit_per_source,
            ): src
            for src in config.sources
        }
        for future in as_completed(futures):
            src = futures[future]
            try:
                posts, stats = future.result()
                all_posts.extend(posts)
                source_stats.append(stats)
                logger.info(f"[{scan_id}] ✓ {stats['label']}: {stats['posts_fetched']} posts")
            except Exception as e:
                label = getattr(src, "resolved_label", str(src))
                logger.error(f"[{scan_id}] ✗ {label}: {e}")
                source_stats.append({"label": label, "posts_fetched": 0, "error": str(e)})

    total_fetched = len(all_posts)
    logger.info(f"[{scan_id}] Total fetched: {total_fetched} posts from {len(source_stats)} sources")

    # 2. Preprocess unified pool
    processed = list(preprocess(all_posts, language_filter=config.language))
    logger.info(f"[{scan_id}] After preprocess: {len(processed)} posts")

    if len(processed) < 10:
        logger.warning(f"[{scan_id}] Too few posts after preprocessing.")
        return ScanResult(
            scan_id=scan_id,
            source="multi",
            target=config.name,
            scan_type=config.scan_type,
            language=config.language,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            model_used=config.model,
            total_posts_fetched=total_fetched,
            total_posts_used=0,
            num_clusters=0,
            sources=source_stats,
            duration_seconds=time.time() - started,
        )

    # 3. Embed
    texts = [p.as_doc_for_embedding() for p in processed]
    embeddings = embed_texts(texts)

    # 4. Cluster
    labels = cluster_embeddings(embeddings)
    unique_clusters = sorted(set(labels) - {-1})
    logger.info(f"[{scan_id}] Found {len(unique_clusters)} clusters")

    # 5. Summarize + source attribution per cluster
    insights_with_posts: list[tuple[dict, list[RawPost]]] = []
    for cluster_id in unique_clusters:
        cluster_posts = [p for p, lbl in zip(processed, labels) if lbl == cluster_id]
        try:
            result = summarize_cluster(
                cluster_posts,
                scan_type=config.scan_type,
                language=config.language,
                model=config.model,
            )
            insight_dict = result.model_dump()
            # Cross-source confirmation — which communities raised this pain
            insight_dict["source_distribution"] = _source_distribution(cluster_posts)
            insights_with_posts.append((insight_dict, cluster_posts))
        except Exception as e:
            logger.error(f"[{scan_id}] Cluster {cluster_id} summarization failed: {e}")

    # 6. Rank + trim
    ranked = _rank_insights(insights_with_posts)[: config.top_n]

    completed_at = datetime.now(timezone.utc)
    return ScanResult(
        scan_id=scan_id,
        source="multi",
        target=config.name,
        scan_type=config.scan_type,
        language=config.language,
        started_at=started_at,
        completed_at=completed_at,
        model_used=config.model,
        total_posts_fetched=total_fetched,
        total_posts_used=len(processed),
        num_clusters=len(unique_clusters),
        insights=ranked,
        sources=source_stats,
        duration_seconds=time.time() - started,
    )
