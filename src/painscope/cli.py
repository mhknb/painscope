"""Typer-based CLI.

Usage:
    painscope scan --source reddit --target r/Turkey --language tr
    painscope list
    painscope show <scan_id>
    painscope mcp-serve
"""

from __future__ import annotations

import json
import logging
import sys

import typer
from rich.console import Console
from rich.table import Table

from painscope.adapters import available_sources
from painscope.output.markdown import save_report
from painscope.pipeline.orchestrator import run_scan
from painscope.storage import get_scan, list_scans, save_scan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)

app = typer.Typer(help="painscope — pain-point and content-idea miner")
console = Console()


@app.command()
def scan(
    source: str = typer.Option(..., help=f"One of: {', '.join(available_sources())}"),
    target: str = typer.Option(..., help="Source-specific target (e.g. 'r/Turkey')"),
    scan_type: str = typer.Option("pain_points", help="pain_points or content_ideas"),
    language: str = typer.Option("tr", help="Content language: tr or en"),
    limit: int = typer.Option(500, help="Max posts to fetch"),
    top_n: int = typer.Option(15, help="Top N insights to return"),
    model: str | None = typer.Option(None, help="OpenRouter model id (overrides default)"),
    output_json: bool = typer.Option(False, "--json", help="Print JSON to stdout instead of markdown path"),
) -> None:
    """Run a scan end-to-end and save results."""
    result = run_scan(
        source=source,
        target=target,
        scan_type=scan_type,  # type: ignore[arg-type]
        language=language,
        limit=limit,
        top_n=top_n,
        model=model,
    )
    save_scan(result)
    report_path = save_report(result)

    if output_json:
        payload = {
            "scan_id": result.scan_id,
            "source": result.source,
            "target": result.target,
            "report_path": str(report_path),
            "insights": result.insights,
            "total_posts_used": result.total_posts_used,
            "num_clusters": result.num_clusters,
            "duration_seconds": result.duration_seconds,
        }
        print(json.dumps(payload, ensure_ascii=False, default=str))
    else:
        console.print(f"[green]✓[/green] Scan complete: [bold]{result.scan_id}[/bold]")
        console.print(f"  Posts used: {result.total_posts_used}")
        console.print(f"  Clusters:   {result.num_clusters}")
        console.print(f"  Insights:   {len(result.insights)}")
        console.print(f"  Duration:   {result.duration_seconds:.1f}s")
        console.print(f"  Report:     [cyan]{report_path}[/cyan]")


@app.command("list")
def list_cmd(
    source: str | None = typer.Option(None),
    target: str | None = typer.Option(None),
    scan_type: str | None = typer.Option(None),
    limit: int = typer.Option(50),
) -> None:
    """List recent scans."""
    rows = list_scans(source=source, target=target, scan_type=scan_type, limit=limit)
    if not rows:
        console.print("[yellow]No scans found.[/yellow]")
        return
    table = Table(title="Recent scans")
    for col in ("scan_id", "source", "target", "type", "lang", "posts", "clusters", "duration"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["scan_id"],
            r["source"],
            r["target"],
            r["scan_type"],
            r["language"],
            str(r["total_posts_used"]),
            str(r["num_clusters"]),
            f"{r['duration_seconds']:.1f}s",
        )
    console.print(table)


@app.command()
def show(scan_id: str) -> None:
    """Print the markdown report for a past scan."""
    data = get_scan(scan_id)
    if not data:
        console.print(f"[red]Scan {scan_id!r} not found.[/red]")
        raise typer.Exit(1)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


@app.command("topic-scan")
def topic_scan_cmd(
    profile: str | None = typer.Option(None, help="Built-in profile: tr, global"),
    config: str | None = typer.Option(None, help="Path to a custom topic YAML config file"),
    scan_type: str | None = typer.Option(None, help="Override scan type: pain_points or content_ideas"),
    output_json: bool = typer.Option(False, "--json", help="Print JSON to stdout"),
) -> None:
    """Run a multi-source scan using a profile or config file.

    Examples:
      painscope topic-scan --profile tr
      painscope topic-scan --profile global --scan-type content_ideas
      painscope topic-scan --config ~/topics/yapay-zeka.yaml
    """
    from painscope.topics import load_config_file, load_profile, list_available_profiles
    from painscope.pipeline.orchestrator import run_topic_scan

    if not profile and not config:
        console.print("[red]Provide --profile or --config.[/red]")
        console.print(f"Available profiles: {', '.join(list_available_profiles())}")
        raise typer.Exit(1)

    if profile and config:
        console.print("[red]Use --profile OR --config, not both.[/red]")
        raise typer.Exit(1)

    topic_config = load_profile(profile) if profile else load_config_file(config)

    if scan_type:
        topic_config = topic_config.model_copy(update={"scan_type": scan_type})

    console.print(f"[bold]{topic_config.name}[/bold] — {len(topic_config.sources)} sources, language={topic_config.language}")

    result = run_topic_scan(topic_config)
    save_scan(result)
    report_path = save_report(result)

    if output_json:
        payload = {
            "scan_id": result.scan_id,
            "target": result.target,
            "sources": result.sources,
            "report_path": str(report_path),
            "insights": result.insights,
            "total_posts_used": result.total_posts_used,
            "num_clusters": result.num_clusters,
            "duration_seconds": result.duration_seconds,
        }
        print(json.dumps(payload, ensure_ascii=False, default=str))
    else:
        console.print(f"[green]✓[/green] Scan complete: [bold]{result.scan_id}[/bold]")
        for s in result.sources:
            status = "[red]✗[/red]" if s.get("error") else "[green]✓[/green]"
            console.print(f"  {status} {s['label']}: {s.get('posts_fetched', 0)} posts")
        console.print(f"  Posts used:   {result.total_posts_used}")
        console.print(f"  Clusters:     {result.num_clusters}")
        console.print(f"  Insights:     {len(result.insights)}")
        console.print(f"  Duration:     {result.duration_seconds:.1f}s")
        console.print(f"  Report:       [cyan]{report_path}[/cyan]")


@app.command("profiles")
def list_profiles_cmd() -> None:
    """List available built-in and user profiles."""
    from painscope.topics import list_available_profiles, USER_PROFILES_DIR

    profiles = list_available_profiles()
    console.print("[bold]Available profiles:[/bold]")
    for p in profiles:
        console.print(f"  {p}")
    console.print(f"\n[dim]Add custom profiles to: {USER_PROFILES_DIR}[/dim]")


@app.command("mcp-serve")
def mcp_serve(
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8765),
) -> None:
    """Start the MCP server (for OpenClaw / OpenCode / Claude Desktop / Cursor)."""
    from painscope.mcp_server import run_mcp_server

    run_mcp_server(host=host, port=port)


if __name__ == "__main__":
    app()
