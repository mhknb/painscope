"""Embedding stage. Uses sentence-transformers locally (CPU-friendly).

Default model: multilingual-e5-base. Works well on Turkish + English.
For better Turkish quality at higher cost, try multilingual-e5-large or
BAAI/bge-m3. Change via config.embedding_model.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from painscope.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    name = get_settings().embedding_model
    logger.info(f"Loading embedding model: {name}")
    return SentenceTransformer(name)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a list of texts. Returns (N, D) float32 array."""
    if not texts:
        return np.zeros((0, 768), dtype=np.float32)

    # The e5 family expects "query: " or "passage: " prefix for best results
    model_name = get_settings().embedding_model
    if "e5" in model_name.lower():
        texts = [f"passage: {t}" for t in texts]

    logger.info(f"Embedding {len(texts)} texts")
    embeddings = _model().encode(
        texts,
        batch_size=32,
        show_progress_bar=len(texts) > 100,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.astype(np.float32)
