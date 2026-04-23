"""Clustering stage. HDBSCAN with optional UMAP dimensionality reduction.

For small N (<200) we skip UMAP and cluster directly on cosine distance.
For larger N we reduce to 15 dims first — this dramatically improves
HDBSCAN quality on noisy social text.
"""

from __future__ import annotations

import logging

import hdbscan
import numpy as np
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)


def cluster(
    embeddings: np.ndarray,
    *,
    min_cluster_size: int = 5,
    min_samples: int | None = None,
) -> np.ndarray:
    """Return a 1-D array of cluster labels. -1 means noise (unclustered)."""
    n = embeddings.shape[0]
    if n < min_cluster_size:
        logger.warning(f"Too few posts ({n}) for clustering; returning all noise.")
        return np.full(n, -1, dtype=int)

    # Normalize — we want cosine-like similarity via euclidean on unit vectors
    X = normalize(embeddings)

    # UMAP reduction for large N
    if n > 200:
        try:
            import umap  # lazy import; heavy

            logger.info(f"Reducing {embeddings.shape} with UMAP → 15 dims")
            reducer = umap.UMAP(
                n_components=15,
                n_neighbors=min(15, n - 1),
                min_dist=0.0,
                metric="cosine",
                random_state=42,
            )
            X = reducer.fit_transform(X)
        except Exception as e:
            logger.warning(f"UMAP failed, clustering on raw embeddings: {e}")

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples or max(2, min_cluster_size // 2),
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(X)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int((labels == -1).sum())
    logger.info(f"Clustering: {n_clusters} clusters, {n_noise}/{n} noise points")

    return labels
