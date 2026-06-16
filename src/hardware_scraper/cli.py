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
    source: str = typer.Option("offerup", "--source", "-s", help="Marketplace source (offerup)"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max listings to scrape"),
) -> None:
    """Scrape listings from a local marketplace."""
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
def report(
    min_margin: Optional[int] = typer.Option(None, "--min-margin", help="Minimum margin % to display"),
    export_csv: bool = typer.Option(False, "--csv", help="Export results to CSV"),
) -> None:
    """Display top opportunities ranked by profit margin."""
    from hardware_scraper.output.reporter import run_report
    run_report(min_margin=min_margin, export_csv=export_csv)


@app.command()
def db_upgrade() -> None:
    """Apply pending Alembic migrations."""
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    console.print("[green]Database upgraded.[/green]")


if __name__ == "__main__":
    app()
