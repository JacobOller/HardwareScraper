from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import AsyncIterator, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hardware_scraper.config import get_config
from hardware_scraper.db import make_engine
from hardware_scraper.models import Listing, Product, ListingProduct
from hardware_scraper.parsers.category_rules import is_accessory_noise, is_refurb_noise
from hardware_scraper.parsers.title_parser import ParsedTitle, TitleParser
from hardware_scraper.scrapers.base import RawListing

# Titles that say "see description" or similar without giving condition clues
_SEE_DESC_RE = re.compile(
    r"\b(see\s+(desc(ription)?|details?|photos?|pics?)|read\s+below|as\s+(described|pictured))\b",
    re.IGNORECASE,
)


async def run_ingest(
    query: Optional[str] = None,
    source: str = "offerup",
    limit: int = 50,
    scraper=None,
) -> None:
    from rich.console import Console

    cfg = get_config()
    console = Console()
    engine = make_engine(cfg.database.url)
    parser = TitleParser()
    llm_parser = _make_llm_parser(cfg, console)

    queries = [query] if query else cfg.search.queries
    if not queries:
        console.print("[red]No search queries configured. Set search.queries in config.yaml or pass --query.[/red]")
        return

    if scraper is None:
        scraper = _make_scraper(cfg, source)
    new_count = 0
    skip_count = 0
    noise_count = 0

    with Session(engine) as db:
        for q in queries:
            console.print(f"[cyan]Scraping {source}: {q!r}[/cyan]")
            async for raw in scraper.search(q, limit=limit):
                stored, skipped, noise = _store_listing(db, raw, parser, llm_parser, cfg)
                new_count += stored
                skip_count += skipped
                noise_count += noise
                if stored:
                    db.commit()  # commit per listing so parallel sources don't contend on DB lock

    console.print(
        f"[green]Done. New: {new_count} | Skipped (duplicate): {skip_count} | Filtered (noise): {noise_count}[/green]"
    )


async def run_browse(limit: int = 100, source: str = "offerup", scraper=None) -> None:
    from rich.console import Console

    cfg = get_config()
    console = Console()
    engine = make_engine(cfg.database.url)
    parser = TitleParser()
    llm_parser = _make_llm_parser(cfg, console)

    if scraper is None:
        scraper = _make_scraper(cfg, source)
    new_count = 0
    skip_count = 0
    noise_count = 0

    console.print(f"[cyan]Browsing all local {source} listings...[/cyan]")
    with Session(engine) as db:
        async for raw in scraper.browse(limit=limit):
            stored, skipped, noise = _store_listing(db, raw, parser, llm_parser, cfg)
            new_count += stored
            skip_count += skipped
            noise_count += noise
            if stored:
                db.commit()  # commit per listing so parallel sources don't contend on DB lock

    console.print(
        f"[green]Done. New: {new_count} | Skipped (duplicate): {skip_count} | Filtered (noise): {noise_count}[/green]"
    )


def _store_listing(db, raw: RawListing, parser: TitleParser, llm_parser, cfg) -> tuple[int, int, int]:
    # Drop refurb reseller noise before touching the DB
    if is_refurb_noise(raw.title):
        return 0, 0, 1

    # Drop accessories misidentified as parent products (phone cases, console games, etc.)
    if is_accessory_noise(raw.title):
        return 0, 0, 1

    # Drop listings with failed price scraping
    if raw.price is None or raw.price <= 0:
        return 0, 0, 1

    existing = db.execute(
        select(Listing).where(
            Listing.source == raw.source,
            Listing.external_id == raw.external_id,
        )
    ).scalar_one_or_none()

    if existing:
        return 0, 1, 0

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
        is_local_pickup=raw.is_local_pickup,
        status="new",
    )
    db.add(listing)
    db.flush()

    parsed = parser.parse(raw.title, raw.description or "")

    if llm_parser and parsed.confidence < cfg.llm.confidence_threshold:
        parsed = llm_parser.parse(raw.title, raw.description or "")

    # For identified hardware with vague condition clues, ask LLM to check description
    if (
        llm_parser
        and parsed.condition == "used"
        and parsed.category
        and raw.description
        and _SEE_DESC_RE.search(raw.title)
    ):
        refined = llm_parser.check_condition(raw.title, raw.description, parsed.category)
        if refined and refined != "used":
            parsed = replace(parsed, condition=refined)

    if parsed.canonical_name and parsed.confidence >= 0.5:
        product = db.execute(
            select(Product).where(Product.canonical_name == parsed.canonical_name)
        ).scalar_one_or_none()

        if not product:
            try:
                with db.begin_nested():
                    product = Product(
                        category=parsed.category or "unknown",
                        brand=parsed.brand,
                        model=parsed.model,
                        canonical_name=parsed.canonical_name,
                        specs=parsed.specs,
                    )
                    db.add(product)
                    db.flush()
            except IntegrityError:
                # Another parallel source inserted this product first; re-query.
                product = db.execute(
                    select(Product).where(Product.canonical_name == parsed.canonical_name)
                ).scalar_one()

        link = ListingProduct(
            listing_id=listing.id,
            product_id=product.id,
            confidence=parsed.confidence,
            condition=parsed.condition,
        )
        db.add(link)
        listing.status = "identified"

    return 1, 0, 0


def _make_scraper(cfg, source: str = "offerup"):
    if source == "facebook":
        from hardware_scraper.scrapers.facebook import FacebookMarketplaceScraper
        return FacebookMarketplaceScraper(
            session_dir=cfg.facebook.session_dir,
            rate_limit_seconds=cfg.scraping.rate_limit_seconds,
            headless=cfg.facebook.headless,
            latitude=cfg.facebook.latitude,
            longitude=cfg.facebook.longitude,
            radius_miles=cfg.facebook.radius_miles,
            city_marketplace_url=cfg.facebook.city_marketplace_url,
        )

    if source == "craigslist":
        from hardware_scraper.scrapers.craigslist import CraigslistScraper
        return CraigslistScraper(
            subdomain=cfg.craigslist.subdomain,
            zip_code=cfg.scraping.location_zip,
            radius_miles=cfg.scraping.radius_miles,
            rate_limit_seconds=cfg.scraping.rate_limit_seconds,
        )

    if source == "ebay_local":
        from hardware_scraper.scrapers.ebay_local import EbayLocalScraper
        return EbayLocalScraper(
            zip_code=cfg.scraping.location_zip,
            radius_miles=cfg.scraping.radius_miles,
            rate_limit_seconds=cfg.scraping.rate_limit_seconds,
            headless=cfg.scraping.headless,
            buy_it_now_only=cfg.ebay_local.buy_it_now_only,
        )

    if source == "mercari":
        from hardware_scraper.scrapers.mercari import MercariScraper
        return MercariScraper(
            rate_limit_seconds=cfg.scraping.rate_limit_seconds,
            headless=cfg.scraping.headless,
        )

    from hardware_scraper.scrapers.offerup import OfferUpScraper
    return OfferUpScraper(
        session_dir=cfg.scraping.session_dir,
        zip_code=cfg.scraping.location_zip,
        radius_miles=cfg.scraping.radius_miles,
        rate_limit_seconds=cfg.scraping.rate_limit_seconds,
        headless=cfg.scraping.headless,
    )


def _make_llm_parser(cfg, console):
    if not cfg.llm.enabled:
        return None
    import os
    from hardware_scraper.parsers.llm_parser import LLMParser
    api_key = cfg.llm.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        console.print("[yellow]LLM enabled but no API key found. Set llm.api_key in config.yaml or ANTHROPIC_API_KEY env var.[/yellow]")
        return None
    return LLMParser(api_key=api_key, model=cfg.llm.model)
