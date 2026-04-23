"""FastMCP server — exposes painscope tools to MCP clients.

Transport: streamable-http (stateless)
Endpoint:  POST /mcp

Tools exposed:
  run_topic_scan     - run a multi-source topic scan
  list_past_scans    - list stored scans
  get_scan_details   - fetch a single scan with insights
  build_scan_config  - convert natural language query → YAML config
  schedule_recurring_scan - register a recurring scan schedule
  list_schedules     - list active schedules
  compare_scans      - diff two scans by insight similarity
  trend_report       - trend analysis across multiple scans for a topic
  deactivate_schedule - stop a recurring schedule
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

import yaml

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "painscope",
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


# ---------------------------------------------------------------------------
# Embedding model warm-up (runs in background at startup)
# ---------------------------------------------------------------------------

def _warmup_embedding_model() -> None:
    def _load() -> None:
        try:
            from painscope.pipeline.embed import _model
            _model()
            logger.info("[painscope] Embedding model warmed up.")
        except Exception as e:
            logger.warning(f"[painscope] Embedding warm-up failed: {e}")

    t = threading.Thread(target=_load, daemon=True, name="embed-warmup")
    t.start()


# ---------------------------------------------------------------------------
# APScheduler for recurring scans
# ---------------------------------------------------------------------------

def _run_overdue_schedules() -> None:
    from painscope.storage import (
        get_overdue_schedules,
        update_schedule_after_run,
    )
    from painscope.mcp_server import _execute_scan_from_yaml

    overdue = get_overdue_schedules()
    for sched in overdue:
        try:
            logger.info(f"[scheduler] Running overdue schedule {sched['schedule_id']} ({sched['topic_name']})")
            _execute_scan_from_yaml(sched["config_yaml"], topic_name=sched["topic_name"])
            update_schedule_after_run(sched["schedule_id"])
        except Exception as e:
            logger.error(f"[scheduler] Schedule {sched['schedule_id']} failed: {e}")


def _start_scheduler() -> None:
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(_run_overdue_schedules, "interval", minutes=30, id="overdue_check")
        scheduler.start()
        logger.info("[painscope] APScheduler started (checking overdue schedules every 30 min)")
    except ImportError:
        logger.warning("[painscope] APScheduler not installed; recurring scans disabled.")
    except Exception as e:
        logger.error(f"[painscope] APScheduler startup failed: {e}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _save_scan(result: Any, *, topic_name: str | None = None) -> None:
    from painscope.storage import save_scan
    from painscope.output.markdown import save_report
    save_scan(result, topic_name=topic_name)
    try:
        save_report(result)
    except Exception as e:
        logger.warning(f"[painscope] Markdown report save failed: {e}")


def _execute_scan_from_yaml(config_yaml: str, *, topic_name: str | None = None) -> dict:
    """Parse a YAML config and run the corresponding scan."""
    from painscope.pipeline.orchestrator import run_scan, run_topic_scan as _run_topic_scan
    from painscope.topics import TopicConfig

    cfg = yaml.safe_load(config_yaml)
    if not isinstance(cfg, dict):
        raise ValueError("config_yaml must be a YAML mapping")

    if "sources" in cfg:
        topic_config = TopicConfig(**cfg)
        result = _run_topic_scan(topic_config)
    else:
        result = run_scan(
            source=cfg.get("source", "reddit"),
            target=cfg.get("target", ""),
            scan_type=cfg.get("scan_type", "pain_points"),
            language=cfg.get("language", "en"),
            limit=cfg.get("limit", 500),
            top_n=cfg.get("top_n", 15),
            model=cfg.get("model"),
        )

    _save_scan(result, topic_name=topic_name or cfg.get("topic_name") or cfg.get("name"))
    return result.__dict__ if hasattr(result, "__dict__") else dict(result)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def run_topic_scan(
    profile: str | None = None,
    config_yaml: str | None = None,
    scan_type: str | None = None,
    topic_name: str | None = None,
) -> dict[str, Any]:
    """Run a multi-source topic scan.

    Args:
        profile:     Built-in profile name (tr, global) or None
        config_yaml: Full YAML configuration string (overrides profile)
        scan_type:   Override scan type: pain_points or content_ideas
        topic_name:  Logical topic label for trend tracking (e.g. "ai-healthcare")

    Returns:
        Scan result dict with scan_id, insights, sources, duration_seconds.
    """
    from painscope.topics import load_config_file, load_profile, list_available_profiles
    from painscope.pipeline.orchestrator import run_topic_scan as _run_topic_scan
    import tempfile, os

    if not profile and not config_yaml:
        return {
            "error": "Provide either 'profile' or 'config_yaml'.",
            "available_profiles": list_available_profiles(),
        }

    if config_yaml:
        cfg = yaml.safe_load(config_yaml)
        if not isinstance(cfg, dict):
            return {"error": "config_yaml must be a valid YAML mapping."}
        if topic_name:
            cfg["name"] = topic_name
        from painscope.topics import TopicConfig
        topic_config = TopicConfig(**cfg)
    else:
        topic_config = load_profile(profile)

    if scan_type:
        topic_config = topic_config.model_copy(update={"scan_type": scan_type})

    result = _run_topic_scan(topic_config)
    _save_scan(result, topic_name=topic_name or topic_config.name)

    sources_summary = []
    for s in getattr(result, "sources", []):
        sources_summary.append({
            "label": s.get("label", ""),
            "posts_fetched": s.get("posts_fetched", 0),
            "error": s.get("error"),
        })

    return {
        "scan_id": result.scan_id,
        "topic_name": topic_name or topic_config.name,
        "sources": sources_summary,
        "total_posts_used": result.total_posts_used,
        "num_clusters": result.num_clusters,
        "duration_seconds": round(result.duration_seconds, 1),
        "insights": result.insights,
        "scanned_at": result.completed_at.isoformat(),
    }


@mcp.tool()
def list_past_scans(
    source: str | None = None,
    target: str | None = None,
    scan_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List previously stored scans with their metadata."""
    from painscope.storage import list_scans
    return list_scans(source=source, target=target, scan_type=scan_type, limit=limit)


@mcp.tool()
def get_scan_details(scan_id: str) -> dict | None:
    """Fetch the full details (including all insights) for a specific scan_id."""
    from painscope.storage import get_scan
    return get_scan(scan_id)


@mcp.tool()
def build_scan_config(
    query: str,
    scan_type: str = "pain_points",
    language: str | None = None,
    limit: int = 400,
    top_n: int = 15,
) -> dict[str, Any]:
    """Convert a natural-language research question into a painscope YAML config.

    Args:
        query:     Natural language description, e.g. "AI tools for doctors"
        scan_type: pain_points | content_ideas (default: pain_points)
        language:  Force language (tr/en). Auto-detected if omitted.
        limit:     Max posts to fetch per source (default: 400)
        top_n:     Number of top insights to return (default: 15)

    Returns:
        Dict with 'config_yaml' (ready to pass to run_topic_scan) and
        'explanation' describing the generated configuration.
    """
    try:
        detected_lang = language or _detect_language(query)
        topic = _match_topic(query)
        sources = _build_sources(query, topic, detected_lang)

        config = {
            "name": topic["name"],
            "language": detected_lang,
            "scan_type": scan_type,
            "limit": limit,
            "top_n": top_n,
            "sources": sources,
        }
        config_yaml = yaml.dump(config, allow_unicode=True, sort_keys=False)

        return {
            "config_yaml": config_yaml,
            "topic_name": topic["name"],
            "language": detected_lang,
            "scan_type": scan_type,
            "source_count": len(sources),
            "explanation": (
                f"Query '{query}' mapped to topic '{topic['name']}' "
                f"({detected_lang}). {len(sources)} sources configured."
            ),
        }
    except Exception as e:
        logger.exception("[build_scan_config] failed")
        return {"error": str(e)}


@mcp.tool()
def schedule_recurring_scan(
    topic_name: str,
    config_yaml: str,
    interval_days: int = 7,
) -> dict[str, Any]:
    """Register a recurring scan that runs automatically every N days.

    Args:
        topic_name:    Logical name for the topic (used for trend tracking)
        config_yaml:   YAML config (from build_scan_config or hand-crafted)
        interval_days: How often to run (7=weekly, 14=bi-weekly, 30=monthly, 90=quarterly)

    Returns:
        Schedule record with schedule_id and next_run_at.
    """
    from painscope.storage import save_schedule
    schedule_id = str(uuid.uuid4())[:8]
    return save_schedule(schedule_id, topic_name, config_yaml, interval_days)


@mcp.tool()
def list_schedules(active_only: bool = True) -> list[dict]:
    """List registered recurring scan schedules."""
    from painscope.storage import list_schedules as _list_schedules
    return _list_schedules(active_only=active_only)


@mcp.tool()
def compare_scans(scan_id_old: str, scan_id_new: str) -> dict[str, Any]:
    """Compare two scans and identify persistent, new, and gone insights.

    Args:
        scan_id_old: Earlier scan ID
        scan_id_new: More recent scan ID

    Returns:
        Dict with 'persistent', 'new', 'gone' insight lists.
    """
    from painscope.storage import get_scan
    from painscope.pipeline.trend import match_insights

    old = get_scan(scan_id_old)
    new = get_scan(scan_id_new)

    if not old:
        return {"error": f"Scan not found: {scan_id_old}"}
    if not new:
        return {"error": f"Scan not found: {scan_id_new}"}

    comparison = match_insights(old["insights"], new["insights"])
    return {
        "old_scan_id": scan_id_old,
        "new_scan_id": scan_id_new,
        "old_scanned_at": old.get("started_at"),
        "new_scanned_at": new.get("started_at"),
        "persistent_count": len(comparison["persistent"]),
        "new_count": len(comparison["new"]),
        "gone_count": len(comparison["gone"]),
        "persistent": [
            {
                "old_body": p["old"].get("body", ""),
                "new_body": p["new"].get("body", ""),
                "similarity": p["similarity"],
            }
            for p in comparison["persistent"][:10]
        ],
        "new_insights": [i.get("body", "") for i in comparison["new"][:10]],
        "gone_insights": [i.get("body", "") for i in comparison["gone"][:10]],
    }


@mcp.tool()
def trend_report(
    topic_name: str,
    max_scans: int = 10,
) -> dict[str, Any]:
    """Generate a trend report for a topic across all its historical scans.

    Args:
        topic_name: The topic label used when scans were stored
        max_scans:  Max historical scans to include (most recent N)

    Returns:
        Trend report with rising, falling, persistent, and one-off insights.
    """
    from painscope.storage import get_scans_for_topic
    from painscope.pipeline.trend import compute_trend_report

    scans = get_scans_for_topic(topic_name, limit=max_scans)
    if len(scans) < 2:
        return {
            "error": f"Need at least 2 scans for topic '{topic_name}'. Found: {len(scans)}.",
            "topic_name": topic_name,
            "scan_count": len(scans),
            "tip": "Use schedule_recurring_scan to automate future scans.",
        }

    report = compute_trend_report(scans)
    return report


@mcp.tool()
def deactivate_schedule(schedule_id: str) -> dict[str, Any]:
    """Deactivate (stop) a recurring scan schedule.

    Args:
        schedule_id: The schedule ID from list_schedules

    Returns:
        Dict with success status.
    """
    from painscope.storage import deactivate_schedule as _deactivate
    ok = _deactivate(schedule_id)
    return {
        "success": ok,
        "schedule_id": schedule_id,
        "message": "Schedule deactivated." if ok else "Schedule not found.",
    }


# ---------------------------------------------------------------------------
# build_scan_config internals
# ---------------------------------------------------------------------------

_TOPIC_KB = [
    {
        "name": "ai-healthcare",
        "keywords": ["doctor", "doktor", "health", "sağlık", "medical", "tıp", "nurse", "hemşire",
                     "dental", "diş", "physician", "clinician", "hospital", "hastane", "ai for doctors",
                     "yapay zeka doktor", "healthcare ai", "clinical ai"],
        "subreddits": ["r/medicine", "r/healthcare", "r/Dentistry", "r/medicalschool",
                       "r/nursing", "r/ArtificialIntelligence"],
        "youtube_queries": ["AI tools for doctors 2024", "artificial intelligence medical education",
                            "AI healthcare professionals tutorial"],
        "appstore_apps": ["Epic MyChart", "Doximity"],
        "producthunt_topic": "health-and-fitness",
    },
    {
        "name": "ai-productivity",
        "keywords": ["productivity", "verimlilik", "workflow", "automation", "otomasyon",
                     "notion", "obsidian", "task manager", "gtd"],
        "subreddits": ["r/productivity", "r/Notion", "r/ObsidianMD", "r/workflow"],
        "youtube_queries": ["AI productivity tools 2024", "notion AI review"],
        "appstore_apps": ["Notion", "Todoist"],
        "producthunt_topic": "productivity",
    },
    {
        "name": "ai-education",
        "keywords": ["education", "eğitim", "learning", "öğrenme", "student", "öğrenci",
                     "teacher", "öğretmen", "course", "kurs", "e-learning"],
        "subreddits": ["r/Education", "r/learnprogramming", "r/Teachers", "r/edtech"],
        "youtube_queries": ["AI in education 2024", "AI tools for students teachers"],
        "appstore_apps": ["Duolingo", "Khan Academy"],
        "producthunt_topic": "education",
    },
    {
        "name": "saas-pain-points",
        "keywords": ["saas", "startup", "software", "product", "b2b", "subscription", "pricing"],
        "subreddits": ["r/SaaS", "r/startups", "r/Entrepreneur", "r/microsaas"],
        "youtube_queries": ["SaaS pain points 2024", "SaaS customer complaints"],
        "appstore_apps": [],
        "producthunt_topic": "saas",
    },
    {
        "name": "ecommerce-sellers",
        "keywords": ["etsy", "amazon", "seller", "satıcı", "ecommerce", "e-ticaret",
                     "shopify", "dropshipping", "online store"],
        "subreddits": ["r/Etsy", "r/AmazonSeller", "r/shopify", "r/ecommerce"],
        "youtube_queries": ["Etsy seller problems 2024", "Amazon seller complaints"],
        "appstore_apps": ["Shopify", "Etsy"],
        "producthunt_topic": "marketing",
    },
    {
        "name": "passive-income",
        "keywords": ["passive income", "pasif gelir", "side hustle", "freelance", "make money",
                     "para kazanma", "remote work", "uzaktan çalışma"],
        "subreddits": ["r/passive_income", "r/freelance", "r/digitalnomad", "r/sidehustle"],
        "youtube_queries": ["passive income ideas 2024", "side hustle pain points"],
        "appstore_apps": [],
        "producthunt_topic": "productivity",
    },
    {
        "name": "developer-tools",
        "keywords": ["developer", "geliştirici", "programming", "programlama", "coding", "api",
                     "github", "devops", "kubernetes", "docker"],
        "subreddits": ["r/programming", "r/webdev", "r/devops", "r/ExperiencedDevs"],
        "youtube_queries": ["developer tool pain points 2024", "coding productivity"],
        "appstore_apps": ["GitHub"],
        "producthunt_topic": "developer-tools",
    },
]

_DEFAULT_TOPIC = {
    "name": "general-research",
    "subreddits": ["r/ArtificialIntelligence", "r/technology"],
    "youtube_queries": [],
    "appstore_apps": [],
    "producthunt_topic": "artificial-intelligence",
}


def _detect_language(text: str) -> str:
    try:
        from langdetect import detect
        lang = detect(text)
        return "tr" if lang == "tr" else "en"
    except Exception:
        turkish_words = {"için", "ile", "bir", "bu", "ve", "da", "de", "mi", "ne", "nasıl",
                         "doktor", "sağlık", "eğitim", "yapay", "zeka", "ama", "çok"}
        if any(w in text.lower().split() for w in turkish_words):
            return "tr"
        return "en"


def _match_topic(query: str) -> dict:
    q_lower = query.lower()
    best = None
    best_score = 0
    for topic in _TOPIC_KB:
        score = sum(1 for kw in topic["keywords"] if kw in q_lower)
        if score > best_score:
            best_score = score
            best = topic
    return best or _DEFAULT_TOPIC


def _en_query(query: str, topic: dict, language: str) -> str:
    if language == "en":
        return query
    translations = {
        "doktor": "doctor", "sağlık": "healthcare", "eğitim": "education",
        "yapay zeka": "artificial intelligence", "diş": "dental", "öğretmen": "teacher",
        "öğrenci": "student", "gelir": "income", "satıcı": "seller",
    }
    result = query.lower()
    for tr, en in translations.items():
        result = result.replace(tr, en)
    return result


def _build_sources(query: str, topic: dict, language: str) -> list[dict]:
    from painscope.adapters import REGISTRY
    available = REGISTRY.available()
    sources = []

    en_q = _en_query(query, topic, language)

    for subreddit in topic.get("subreddits", [])[:4]:
        if "reddit" in available:
            sources.append({"source": "reddit", "target": subreddit})

    if "youtube" in available:
        for yt_q in topic.get("youtube_queries", [])[:2]:
            sources.append({"source": "youtube", "target": yt_q})

    if "appstore" in available:
        for app in topic.get("appstore_apps", [])[:2]:
            sources.append({"source": "appstore", "target": app})

    if "producthunt" in available and topic.get("producthunt_topic"):
        sources.append({"source": "producthunt", "target": topic["producthunt_topic"]})

    if not sources:
        sources.append({"source": "reddit", "target": "r/ArtificialIntelligence"})

    return sources


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

def run_mcp_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    logger.info(f"Starting painscope MCP server on http://{host}:{port}/mcp")
    _warmup_embedding_model()
    _start_scheduler()
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
