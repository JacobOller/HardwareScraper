from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from hardware_scraper.config import get_config
from hardware_scraper.db import make_engine
from hardware_scraper.models import Listing, Valuation

console = Console()

_TIER_COLORS = {1: "bright_green", 2: "green", 3: "yellow", 4: "white", 5: "red"}


def run_report(min_margin: Optional[int] = None, export_csv: bool = False) -> None:
    cfg = get_config()
    engine = make_engine(cfg.database.url)
    threshold = min_margin if min_margin is not None else cfg.output.min_margin_to_show

    with Session(engine) as db:
        rows = (
            db.query(Listing, Valuation)
            .join(Valuation, Valuation.listing_id == Listing.id)
            .filter(Valuation.margin_pct >= threshold)
            .order_by(Valuation.margin_pct.desc())
            .all()
        )

    if not rows:
        console.print("[yellow]No results found. Run `hardware-scraper scrape` then `hardware-scraper valuate`.[/yellow]")
        return

    table = Table(title=f"Hardware Opportunities (margin ≥ {threshold}%)", show_lines=True)
    table.add_column("Title", max_width=40)
    table.add_column("Price", justify="right")
    table.add_column("eBay Median", justify="right")
    table.add_column("Profit", justify="right")
    table.add_column("Margin %", justify="right")
    table.add_column("Tier")
    table.add_column("URL", max_width=40, no_wrap=True)

    for listing, val in rows:
        color = _TIER_COLORS.get(val.margin_tier, "white")
        table.add_row(
            listing.title[:40],
            f"${listing.price:.0f}",
            f"${val.ebay_median_price:.0f}",
            f"[{color}]${val.profit:.0f}[/{color}]",
            f"[{color}]{val.margin_pct:.1f}%[/{color}]",
            f"[{color}]{val.margin_label}[/{color}]",
            listing.url,
        )

    console.print(table)

    if export_csv:
        _export_csv(rows, cfg.output.csv_dir, threshold)


def _export_csv(rows: list, csv_dir: str, threshold: int) -> None:
    os.makedirs(csv_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(csv_dir, f"report_{ts}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "title", "asking_price", "ebay_median", "profit", "margin_pct",
            "margin_tier", "margin_label", "url", "source"
        ])
        for listing, val in rows:
            writer.writerow([
                listing.title, listing.price, val.ebay_median_price,
                val.profit, val.margin_pct, val.margin_tier, val.margin_label,
                listing.url, listing.source,
            ])
    console.print(f"[green]Exported {len(rows)} rows → {path}[/green]")
