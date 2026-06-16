from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from hardware_scraper.config import get_config
from hardware_scraper.models import Listing, Product, ListingProduct
from hardware_scraper.parsers.title_parser import TitleParser
from hardware_scraper.scrapers.offerup import OfferUpScraper


async def run_ingest(
    query: Optional[str] = None,
    source: str = "offerup",
    limit: int = 50,
) -> None:
    from rich.console import Console
    from rich.progress import track

    cfg = get_config()
    console = Console()
    engine = create_engine(cfg.database.url)
    parser = TitleParser()

    queries = [query] if query else cfg.search.queries
    if not queries:
        console.print("[red]No search queries configured. Set search.queries in config.yaml or pass --query.[/red]")
        return

    scraper = OfferUpScraper(
        session_dir=cfg.scraping.session_dir,
        zip_code=cfg.scraping.location_zip,
        radius_miles=cfg.scraping.radius_miles,
        rate_limit_seconds=cfg.scraping.rate_limit_seconds,
        headless=cfg.scraping.headless,
    )

    new_count = 0
    skip_count = 0

    with Session(engine) as db:
        for q in queries:
            console.print(f"[cyan]Scraping OfferUp: {q!r}[/cyan]")
            async for raw in scraper.search(q, limit=limit):
                existing = db.execute(
                    select(Listing).where(
                        Listing.source == raw.source,
                        Listing.external_id == raw.external_id,
                    )
                ).scalar_one_or_none()

                if existing:
                    skip_count += 1
                    continue

                listing = Listing(
                    source=raw.source,
                    external_id=raw.external_id,
                    url=raw.url,
                    title=raw.title,
                    price=raw.price,
                    location=raw.location,
                    description=raw.description,
                    image_urls=json.dumps(raw.image_urls),
                    posted_at=raw.posted_at,
                    status="new",
                )
                db.add(listing)
                db.flush()

                parsed = parser.parse(raw.title, raw.description or "")

                if parsed.canonical_name and parsed.confidence >= 0.5:
                    product = db.execute(
                        select(Product).where(Product.canonical_name == parsed.canonical_name)
                    ).scalar_one_or_none()

                    if not product:
                        product = Product(
                            category=parsed.category or "unknown",
                            brand=parsed.brand,
                            model=parsed.model,
                            canonical_name=parsed.canonical_name,
                            specs=parsed.specs,
                        )
                        db.add(product)
                        db.flush()

                    link = ListingProduct(
                        listing_id=listing.id,
                        product_id=product.id,
                        confidence=parsed.confidence,
                        condition=parsed.condition,
                    )
                    db.add(link)
                    listing.status = "identified"

                new_count += 1

        db.commit()

    console.print(f"[green]Done. New: {new_count} | Skipped (duplicate): {skip_count}[/green]")
