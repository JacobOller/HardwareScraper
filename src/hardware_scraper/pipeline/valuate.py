from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from hardware_scraper.config import get_config
from hardware_scraper.db import make_engine
from hardware_scraper.ebay.client import EbayClient
from hardware_scraper.ebay.comp_fetcher import CompFetcher
from hardware_scraper.models import Listing, ListingProduct, Product, Valuation
from hardware_scraper.valuation.calculator import ValuationCalculator


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

    with Session(engine) as db:
        fetcher = CompFetcher(client=ebay_client, db=db)

        candidates = db.execute(
            select(Listing, ListingProduct, Product)
            .join(ListingProduct, ListingProduct.listing_id == Listing.id)
            .join(Product, Product.id == ListingProduct.product_id)
            .where(
                Listing.status == "identified",
                ListingProduct.confidence >= min_confidence,
            )
        ).all()

        console.print(f"[cyan]Valuating {len(candidates)} listings…[/cyan]")
        valuated = 0
        skipped = 0

        for listing, lp, product in candidates:
            already = db.execute(
                select(Valuation).where(Valuation.listing_id == listing.id)
            ).scalar_one_or_none()
            if already:
                skipped += 1
                continue

            try:
                comps = fetcher.get_cached_comps(product.id, lp.condition)
                if comps is None:
                    comps = await fetcher.fetch_and_cache(product.id, product.canonical_name, lp.condition)

                median, count = fetcher.median_sold_price(comps)
                if count == 0:
                    console.print(f"  [yellow]No comps for {product.canonical_name}, skipping[/yellow]")
                    skipped += 1
                    continue

                result = calculator.calculate(listing.price, median, count, category=product.category)

                val = Valuation(
                    listing_id=listing.id,
                    product_id=product.id,
                    ebay_median_price=result.ebay_median_price,
                    ebay_comp_count=result.ebay_comp_count,
                    estimated_fees=result.estimated_fees,
                    estimated_shipping=result.estimated_shipping,
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

        db.commit()

    console.print(f"[green]Done. Valuated: {valuated} | Skipped: {skipped}[/green]")
