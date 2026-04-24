# syntax=docker/dockerfile:1.7

# ── Stage 1: builder ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG PRELOAD_EMBEDDING_MODEL=false

# System deps needed by hdbscan/umap-learn/sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy project files
COPY pyproject.toml README.md ./
COPY src ./src

# Install into a venv we can copy to the runtime stage
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip \
    && pip install filelock fsspec jinja2 networkx sympy typing-extensions \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install .

# Optional: pre-download the default embedding model. Keep this disabled in
# Coolify by default so image builds stay small and reliable.
RUN mkdir -p /root/.cache/huggingface \
    && if [ "$PRELOAD_EMBEDDING_MODEL" = "true" ]; then \
        python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"; \
    fi

# ── Stage 2: runtime ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/data \
    HF_HOME=/opt/hf_cache

# Minimal runtime deps (libgomp needed by hdbscan/umap)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 painscope

# Copy venv + HF cache from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /root/.cache/huggingface /opt/hf_cache

# Data dir (mount a Coolify volume here)
RUN mkdir -p /data && chown -R painscope:painscope /data /opt/hf_cache

USER painscope
WORKDIR /home/painscope

EXPOSE 8765 8787

# Default: run MCP server on 0.0.0.0:8765
# Override with `docker run ... painscope web-serve ...` for the web UI.
ENTRYPOINT ["painscope"]
CMD ["mcp-serve", "--host", "0.0.0.0", "--port", "8765"]
