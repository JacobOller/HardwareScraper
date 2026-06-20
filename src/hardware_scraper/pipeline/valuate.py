from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from hardware_scraper.config import get_config
from hardware_scraper.db import make_engine
from hardware_scraper.ebay.client import EbayClient
from hardware_scraper.ebay.comp_fetcher import CompFetcher
from hardware_scraper.models import Listing, ListingProduct, Product, Valuation
from hardware_scraper.valuation.calculator import ValuationCalculator


MIN_ASKING_PRICE = 10.0   # skip listings priced below this (likely junk/accessories)
MIN_COMP_COUNT   = 2      # require at least this many eBay sold comps for a valid valuation


@asynccontextmanager
async def _ebay_scraper_ctx(use_api: bool) -> AsyncIterator[Optional[object]]:
    """Yield a shared EbayScraper when API is not configured, else yield None."""
    if use_api:
        yield None
    else:
        from hardware_scraper.ebay.scraper import EbayScraper
        async with EbayScraper.session() as scraper:
            yield scraper


@asynccontextmanager
async def _amazon_scraper_ctx(cfg) -> AsyncIterator[Optional[object]]:
    """Yield a shared AmazonScraper when amazon.enabled is true, else yield None."""
    if not cfg.amazon.enabled:
        yield None
    else:
        from hardware_scraper.amazon.scraper import AmazonScraper
        async with AmazonScraper.session(
            session_dir=cfg.amazon.session_dir,
            rate_limit_seconds=cfg.amazon.rate_limit_seconds,
        ) as scraper:
            yield scraper


async def run_valuate(min_confidence: float = 0.7) -> None:
    from rich.console import Console

    cfg = get_config()
    console = Console()
    engine = make_engine(cfg.database.url)

    ebay_client = EbayClient(
        app_id=cfg.ebay.app_id,
        cert_id=cfg.ebay.cert_id,
        environment=cfg.ebay.environment,
    )
    calculator = ValuationCalculator()
    use_api = bool(cfg.ebay.app_id and cfg.ebay.cert_id)
    _amz_cache: Dict[int, Optional[float]] = {}

    async with _ebay_scraper_ctx(use_api) as shared_scraper:
        async with _amazon_scraper_ctx(cfg) as amazon_scraper:
            with Session(engine) as db:
                fetcher = CompFetcher(client=ebay_client, db=db, scraper=shared_scraper)

                candidates = db.execute(
                    select(Listing, ListingProduct, Product)
                    .join(ListingProduct, ListingProduct.listing_id == Listing.id)
                    .join(Product, Product.id == ListingProduct.product_id)
                    .where(
                        Listing.status == "identified",
                        ListingProduct.confidence >= min_confidence,
                    )
                ).all()

                # Pre-load all existing valuation listing_ids — replaces N per-listing DB queries
                existing_ids: set[int] = {
                    row[0] for row in db.execute(select(Valuation.listing_id)).all()
                }

                # Filter to only listings that actually need valuation
                to_valuate = [
                    (listing, lp, product)
                    for listing, lp, product in candidates
                    if listing.id not in existing_ids
                    and (listing.price is None or listing.price >= MIN_ASKING_PRICE)
                ]

                console.print(
                    f"[cyan]Valuating {len(to_valuate)} listings "
                    f"({len(candidates) - len(to_valuate)} already done/skipped)…[/cyan]"
                )

                if not to_valuate:
                    console.print("[green]Nothing to valuate.[/green]")
                    return

                # Build unique (product_id, condition) → canonical_name
                # so we pre-fetch all eBay comps before the valuation loop.
                # for_parts listings also need a "working_used" fetch (handled inside fetch_and_cache).
                pair_to_canonical: Dict[tuple, str] = {}
                for _, lp, product in to_valuate:
                    key = (product.id, lp.condition)
                    if key not in pair_to_canonical:
                        pair_to_canonical[key] = product.canonical_name

                console.print(
                    f"[cyan]Pre-fetching eBay comps for {len(pair_to_canonical)} unique products…[/cyan]"
                )
                for (product_id, condition), canonical_name in pair_to_canonical.items():
                    if fetcher.get_cached_comps(product_id, condition) is None:
                        try:
                            await fetcher.fetch_and_cache(product_id, canonical_name, condition)
                        except Exception as exc:
                            console.print(
                                f"  [yellow]eBay fetch failed for {canonical_name} ({condition}): {exc}[/yellow]"
                            )

                # Valuation loop — all eBay data is in DB cache now; no browser calls here
                console.print("[cyan]Calculating margins…[/cyan]")
                valuated = 0
                skipped = 0
                COMMIT_EVERY = 50

                for i, (listing, lp, product) in enumerate(to_valuate):
                    try:
                        comps = fetcher.get_cached_comps(product.id, lp.condition) or []
                        median, count = fetcher.median_sold_price(comps)
                        if count < MIN_COMP_COUNT:
                            skipped += 1
                            continue

                        working_median: Optional[float] = None
                        working_count: Optional[int] = None
                        if lp.condition == "for_parts":
                            working_comps = fetcher.get_cached_comps(product.id, "working_used") or []
                            wm, wc = fetcher.median_sold_price(working_comps)
                            if wc >= MIN_COMP_COUNT:
                                working_median = wm
                                working_count = wc

                        inbound_shipping = 0.0
                        if not listing.is_local_pickup:
                            inbound_shipping = cfg.shipping.for_category(product.category)

                        amazon_price: Optional[float] = None
                        if amazon_scraper is not None:
                            if product.id not in _amz_cache:
                                try:
                                    _amz_cache[product.id] = await amazon_scraper.get_price(
                                        product.canonical_name
                                    )
                                except Exception as exc:
                                    console.print(
                                        f"  [yellow]Amazon price fetch failed for {product.canonical_name}: {exc}[/yellow]"
                                    )
                                    _amz_cache[product.id] = None
                            amazon_price = _amz_cache[product.id]

                        result = calculator.calculate(
                            listing.price, median, count,
                            category=product.category,
                            inbound_shipping=inbound_shipping,
                            amazon_price=amazon_price,
                            working_comp_price=working_median,
                            working_comp_count=working_count,
                        )

                        val = Valuation(
                            listing_id=listing.id,
                            product_id=product.id,
                            ebay_median_price=result.ebay_median_price,
                            ebay_comp_count=result.ebay_comp_count,
                            estimated_fees=result.estimated_fees,
                            estimated_shipping=result.estimated_shipping,
                            inbound_shipping=result.inbound_shipping,
                            amazon_price=result.amazon_price,
                            working_comp_price=result.working_comp_price,
                            working_comp_count=result.working_comp_count,
                            net_resale=result.net_resale,
                            profit=result.profit,
                            margin_pct=result.margin_pct,
                            margin_tier=result.margin_tier,
                            margin_label=result.margin_label,
                        )
                        db.add(val)
                        listing.status = "valuated"
                        valuated += 1

                    except Exception as exc:
                        console.print(f"  [red]Error valuating listing {listing.id}: {exc}[/red]")
                        skipped += 1

                    if (i + 1) % COMMIT_EVERY == 0:
                        db.commit()
                        console.print(f"  [dim]Committed {valuated} valuations so far…[/dim]")

                db.commit()

    console.print(f"[green]Done. Valuated: {valuated} | Skipped: {skipped}[/green]")
