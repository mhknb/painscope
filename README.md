# painscope

Legal-source pain-point and content-idea miner.

Scans Reddit (and soon YouTube, App Store reviews, Hacker News, Stack Exchange, GitHub), clusters posts by topic, and uses any LLM of your choice via OpenRouter to extract ranked pain points or content ideas. Output: Markdown reports you read in Obsidian, Notion, or anywhere.

Built as a personal research tool. LLM-agnostic (OpenRouter). Runtime-agnostic (CLI, MCP server, Docker). No SaaS dependencies.

## Why this exists

Existing tools like PainPointy cover English Reddit well. None cover Turkish subreddits + Turkish YouTube comments + Turkish App Store reviews with a unified Turkish NLP pipeline. This tool does — from **legal, ToS-compliant sources only** (no scraping of sites that prohibit it).

## Architecture

```
┌───────────────┐
│  CLI          │  painscope scan --source reddit --target r/Turkey
│  MCP server   │  (for OpenClaw / OpenCode / Claude Desktop / Cursor)
└───────┬───────┘
        │
┌───────▼────────────────────────────────────────────┐
│ Orchestrator                                       │
│   fetch → preprocess → embed → cluster → summarize │
└───────┬────────────────────────────────────────────┘
        │
        ├── Adapters (Reddit today; YouTube/HN/AppStore/SE/GitHub next)
        ├── Preprocess (PII scrub, lang detect, dedup)
        ├── Embed (local sentence-transformers, multilingual-e5)
        ├── Cluster (HDBSCAN + UMAP)
        └── Summarize (any OpenRouter model — TR/EN prompts)
        │
┌───────▼────────┐
│ SQLite storage │  history, comparison, trend tracking
│ Markdown reports ├──► ~/.painscope/reports/
└────────────────┘
```

**Design principle:** model layer uses OpenRouter, so you swap models per call or in config without touching code. Embeddings stay local (free, Turkish-capable, no per-call cost).

## Setup

### Prerequisites

- Python 3.11+
- Reddit API credentials: create a **script**-type app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
- OpenRouter API key with credits: [openrouter.ai](https://openrouter.ai)

### Install (local dev, uv recommended)

```bash
git clone <your-repo> painscope
cd painscope
cp .env.example .env
# Edit .env with your keys

# With uv (fast):
uv sync
uv run painscope --help

# With pip:
pip install -e .
painscope --help
```

First scan downloads the embedding model (~500MB, one-time) unless you build the Docker image with `PRELOAD_EMBEDDING_MODEL=true`.

### Install (Docker)

```bash
cp .env.example .env
# Edit .env
docker compose build
docker compose up -d
```

MCP runs on `http://localhost:8767/mcp` by default; the personal web UI runs on `http://127.0.0.1:8787` by default.
On a VPS, keep `WEB_BIND_IP=127.0.0.1` and use an SSH tunnel:

```bash
ssh -L 8787:127.0.0.1:8787 root@<server>
```

### Install (Coolify)

1. In Coolify, create a new **Docker Compose** resource.
2. Point it at your repo (or paste `docker-compose.yml`).
3. Set environment variables in the Coolify UI (do not commit `.env`).
4. Set the `painscope_data` and `painscope_hf_cache` volumes to persistent.
5. Prefer keeping the web UI private behind an SSH tunnel, VPN, or Coolify internal network.
   If you expose it through a public domain, set `WEB_BIND_IP=0.0.0.0` and a strong `PAINSCOPE_WEB_PASSWORD`.
6. Deploy. The first scan may take longer while the embedding model is downloaded.

## Usage

### CLI

```bash
# Turkish pain points from r/Turkey
painscope scan --source reddit --target r/Turkey --scan-type pain_points --language tr

# English content ideas from r/saas
painscope scan --source reddit --target r/saas --scan-type content_ideas --language en

# Use a specific OpenRouter model (overrides default)
painscope scan --source reddit --target r/KGBTR --language tr \
    --model qwen/qwen-2.5-72b-instruct

# See recent scans
painscope list

# Inspect a past scan as JSON
painscope show 20260422-103015-reddit-r_Turkey

# Start MCP server (for agent use)
painscope mcp-serve --host 0.0.0.0 --port 8765

# Start personal web UI
painscope web-serve --host 0.0.0.0 --port 8787
```

Every scan writes a Markdown report to `~/.painscope/reports/<scan_id>.md` and persists the full result to SQLite at `~/.painscope/painscope.db`.

### MCP (from OpenClaw, OpenCode, Claude Desktop, Cursor, etc.)

Once `painscope mcp-serve` is running (or the Docker container is up), point any MCP-aware client at `http://<host>:8765/mcp`.

Tools exposed:
- `run_scan(source, target, scan_type, language, limit, top_n, model)` — run a new scan
- `list_historical_scans(source?, target?, scan_type?, limit)` — list past scans
- `get_scan_details(scan_id)` — retrieve a past scan with full insights
- `get_scan_report_markdown(scan_id)` — render past scan as markdown
- `list_available_sources()` — supported sources

#### Example: OpenClaw config

Add to your OpenClaw MCP servers config (location depends on your OpenClaw version):

```yaml
mcp_servers:
  - name: painscope
    transport: sse
    url: http://painscope-mcp:8765/sse  # internal Coolify network
```

#### Example: Claude Desktop config

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "painscope": {
      "command": "docker",
      "args": ["exec", "-i", "painscope-mcp", "painscope", "mcp-serve", "--stdio"]
    }
  }
}
```

(Stdio transport for desktop clients requires a small tweak to `run_mcp_server` — easy to add.)

## Choosing an LLM model

OpenRouter gives you ~75 models. For this workload, the trade-offs:

| Model | Per-call cost (rough) | Turkish quality | Notes |
|-------|----------------------|-----------------|-------|
| `google/gemini-2.0-flash-001` | very low | good | Current default |
| `anthropic/claude-haiku-4.5` | low | excellent | Best reasoning at small size |
| `qwen/qwen-2.5-72b-instruct` | low | very good | Strong multilingual, cheap |
| `openai/gpt-4o-mini` | low | good | Solid baseline |
| `mistralai/mistral-large-2411` | medium | good | EU-hosted option |
| `anthropic/claude-opus-4.7` | high | excellent | Overkill for summarization |

Set defaults in `.env`, or override per-scan with `--model`.

## Extending with new sources

To add a new adapter (say, Hacker News):

1. Create `src/painscope/adapters/hackernews.py` implementing `SourceAdapter`:
   - `name = "hackernews"`
   - `validate_target(target) -> str`
   - `fetch(target, limit, language) -> Iterator[RawPost]`
2. Register in `src/painscope/adapters/__init__.py`.
3. Document its `target` format (keyword? story id?) in this README.

**Legal rule:** only add sources with documented legal basis (official API or unambiguous commercial-use permission). No scraping of sites whose ToS prohibits it.

## Troubleshooting

**`Reddit credentials missing`** — fill in `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` in `.env`.

**Embedding model stuck downloading** — first run fetches ~500MB from Hugging Face. Let it finish. On Coolify, this is done at image build time (Dockerfile does it once).

**`Model did not return valid JSON`** — some OpenRouter models are iffy on JSON output. Fall back to `google/gemini-2.0-flash-001` or `anthropic/claude-haiku-4.5` for this workload.

**Scan returns 0 insights** — either the source had < 10 valid posts after preprocessing (likely target is too narrow or very new), or too many were filtered by language (check `--language` flag).

## Data & Privacy

- All data is processed in your own infrastructure (your machine, your Coolify).
- LLM calls go to OpenRouter (which relays to the provider you chose — Google, Anthropic, OpenAI, etc.).
- Embedding model runs locally — never leaves your machine.
- SQLite database at `~/.painscope/painscope.db` (or `/data/painscope.db` in Docker).
- PII patterns are scrubbed at ingestion (emails, phone numbers, TCKN, credit cards).

This tool is built for personal research. If you ever want to offer it as a service, you'll need to add: auth, multi-tenancy, billing, KVKK compliance artifacts, DPAs with processors. The core pipeline stays unchanged.

## License

MIT.
