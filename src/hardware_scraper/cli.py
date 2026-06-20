from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(name="hardware-scraper", help="Find underpriced PC hardware on local marketplaces.")
console = Console()


@app.command()
def scrape(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Override search query"),
    source: str = typer.Option("offerup", "--source", "-s", help="Marketplace source: offerup | facebook"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max listings to scrape"),
) -> None:
    """Scrape listings from a local marketplace by keyword search."""
    from hardware_scraper.pipeline.ingest import run_ingest
    asyncio.run(run_ingest(query=query, source=source, limit=limit))


@app.command()
def valuate(
    min_confidence: float = typer.Option(0.7, "--min-confidence", help="Min identification confidence to valuate"),
) -> None:
    """Run valuation pass on identified listings."""
    from hardware_scraper.pipeline.valuate import run_valuate
    asyncio.run(run_valuate(min_confidence=min_confidence))


@app.command()
def validate(
    margin_threshold: Optional[float] = typer.Option(None, "--margin", help="LLM-check valuations above this margin % (default: llm.validate_margin_threshold in config)"),
) -> None:
    """LLM-validate high-margin listings and drop misrepresentations (accessories, services, etc.)."""
    from hardware_scraper.pipeline.validate import run_llm_validate
    asyncio.run(run_llm_validate(margin_threshold=margin_threshold))


@app.command()
def report(
    min_margin: Optional[int] = typer.Option(None, "--min-margin", help="Minimum margin % to display"),
    export_csv: bool = typer.Option(False, "--csv", help="Export results to CSV"),
) -> None:
    """Display top opportunities ranked by profit margin."""
    from hardware_scraper.output.reporter import run_report
    run_report(min_margin=min_margin, export_csv=export_csv)


@app.command()
def browse(
    limit: int = typer.Option(100, "--limit", "-n", help="Max listings to fetch"),
    source: str = typer.Option("offerup", "--source", "-s", help="Marketplace source: offerup | facebook"),
) -> None:
    """Fetch all local listings without a keyword (empty-query browse)."""
    from hardware_scraper.pipeline.ingest import run_browse
    asyncio.run(run_browse(limit=limit, source=source))


@app.command(name="fb-browse")
def fb_browse(
    limit: int = typer.Option(100, "--limit", "-n", help="Max listings to fetch"),
) -> None:
    """Browse all local Facebook Marketplace listings (shorthand for browse --source facebook)."""
    from hardware_scraper.pipeline.ingest import run_browse
    asyncio.run(run_browse(limit=limit, source="facebook"))


@app.command(name="fb-scrape")
def fb_scrape(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Search query"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max listings to fetch"),
) -> None:
    """Search Facebook Marketplace by keyword (shorthand for scrape --source facebook)."""
    from hardware_scraper.pipeline.ingest import run_ingest
    asyncio.run(run_ingest(query=query, source="facebook", limit=limit))


@app.command(name="cl-scrape")
def cl_scrape(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Search query"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max listings to fetch"),
) -> None:
    """Search Craigslist by keyword."""
    from hardware_scraper.pipeline.ingest import run_ingest
    asyncio.run(run_ingest(query=query, source="craigslist", limit=limit))


@app.command(name="cl-browse")
def cl_browse(
    limit: int = typer.Option(100, "--limit", "-n", help="Max listings to fetch"),
) -> None:
    """Browse Craigslist electronics category (no keyword)."""
    from hardware_scraper.pipeline.ingest import run_browse
    asyncio.run(run_browse(limit=limit, source="craigslist"))


@app.command(name="ebay-local-scrape")
def ebay_local_scrape(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Search query"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max listings to fetch"),
) -> None:
    """Search eBay local pickup listings by keyword."""
    from hardware_scraper.pipeline.ingest import run_ingest
    asyncio.run(run_ingest(query=query, source="ebay_local", limit=limit))


@app.command(name="mercari-scrape")
def mercari_scrape(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Search query"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max listings to fetch"),
) -> None:
    """Search Mercari by keyword."""
    from hardware_scraper.pipeline.ingest import run_ingest
    asyncio.run(run_ingest(query=query, source="mercari", limit=limit))


@app.command()
def scan(
    min_confidence: float = typer.Option(0.5, "--min-confidence", help="Min confidence for valuation"),
) -> None:
    """Full pipeline: browse + scrape all configured queries on all enabled sources + valuate + report."""
    from hardware_scraper.config import get_config
    from hardware_scraper.pipeline.ingest import run_browse, run_ingest, _make_scraper
    from hardware_scraper.pipeline.valuate import run_valuate
    from hardware_scraper.output.reporter import run_report

    cfg = get_config()

    browse_and_search = ["offerup", "facebook"]
    if cfg.craigslist.enabled:
        browse_and_search.append("craigslist")
    if cfg.ebay_local.enabled:
        browse_and_search.append("ebay_local")

    search_only = ["mercari"] if cfg.mercari.enabled else []
    all_search_sources = browse_and_search + search_only

    async def _browse_one(source: str) -> None:
        scraper = _make_scraper(cfg, source)
        async with scraper.session():
            console.print(f"[cyan]Browsing {source}...[/cyan]")
            try:
                await run_browse(source=source, scraper=scraper)
            except Exception as exc:
                console.print(f"[red]Browse {source} error: {exc}[/red]")

    async def _scrape_all_queries(source: str) -> None:
        scraper = _make_scraper(cfg, source)
        async with scraper.session():
            for q in cfg.search.queries:
                console.print(f"[cyan]Scraping {source}: {q!r}...[/cyan]")
                try:
                    await run_ingest(query=q, source=source, scraper=scraper)
                except Exception as exc:
                    console.print(f"[red]Scrape {source} {q!r} error: {exc}[/red]")

    async def _run():
        # Browse all sources in parallel
        await asyncio.gather(*[_browse_one(s) for s in browse_and_search])

        # Search all sources in parallel; each source runs its 34 queries with one browser
        await asyncio.gather(*[_scrape_all_queries(s) for s in all_search_sources])

        console.print("[cyan]Valuating...[/cyan]")
        await run_valuate(min_confidence=min_confidence)

        console.print("[cyan]LLM validating high-margin results...[/cyan]")
        from hardware_scraper.pipeline.validate import run_llm_validate
        await run_llm_validate()

    asyncio.run(_run())
    run_report()


@app.command()
def notify() -> None:
    """AI-confirm top Tier 1/2 deals and send new ones to Discord."""
    from hardware_scraper.pipeline.notify import run_notify
    asyncio.run(run_notify())


@app.command(name="scan-and-notify")
def scan_and_notify(
    min_confidence: float = typer.Option(0.5, "--min-confidence", help="Min confidence for valuation"),
) -> None:
    """Full pipeline (browse + scrape + valuate + validate) then notify Discord."""
    from hardware_scraper.config import get_config
    from hardware_scraper.pipeline.ingest import run_browse, run_ingest, _make_scraper
    from hardware_scraper.pipeline.valuate import run_valuate
    from hardware_scraper.pipeline.validate import run_llm_validate
    from hardware_scraper.pipeline.notify import run_notify

    cfg = get_config()

    browse_and_search = ["offerup", "facebook"]
    if cfg.craigslist.enabled:
        browse_and_search.append("craigslist")
    if cfg.ebay_local.enabled:
        browse_and_search.append("ebay_local")
    search_only = ["mercari"] if cfg.mercari.enabled else []
    all_search_sources = browse_and_search + search_only

    async def _browse_one(source: str) -> None:
        scraper = _make_scraper(cfg, source)
        async with scraper.session():
            console.print(f"[cyan]Browsing {source}...[/cyan]")
            try:
                await run_browse(source=source, scraper=scraper)
            except Exception as exc:
                console.print(f"[red]Browse {source} error: {exc}[/red]")

    async def _scrape_all_queries(source: str) -> None:
        scraper = _make_scraper(cfg, source)
        async with scraper.session():
            for q in cfg.search.queries:
                console.print(f"[cyan]Scraping {source}: {q!r}...[/cyan]")
                try:
                    await run_ingest(query=q, source=source, scraper=scraper)
                except Exception as exc:
                    console.print(f"[red]Scrape {source} {q!r} error: {exc}[/red]")

    async def _run():
        await asyncio.gather(*[_browse_one(s) for s in browse_and_search])
        await asyncio.gather(*[_scrape_all_queries(s) for s in all_search_sources])
        console.print("[cyan]Valuating...[/cyan]")
        await run_valuate(min_confidence=min_confidence)
        console.print("[cyan]LLM validating high-margin results...[/cyan]")
        await run_llm_validate()
        console.print("[cyan]Notifying Discord...[/cyan]")
        await run_notify()

    asyncio.run(_run())


@app.command()
def ui(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to serve on"),
) -> None:
    """Launch the web dashboard on localhost:8000."""
    import uvicorn
    console.print(f"[green]Starting HardwareScraper UI at http://{host}:{port}[/green]")
    uvicorn.run(
        "hardware_scraper.web.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="warning",
    )


@app.command()
def db_upgrade() -> None:
    """Apply pending Alembic migrations."""
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    console.print("[green]Database upgraded.[/green]")


if __name__ == "__main__":
    app()
