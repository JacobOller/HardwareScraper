"""LLM validation pass — drop obvious misrepresentations from high-margin valuations.

Only runs when llm.enabled is true and there are valuations above the margin threshold.
Uses Claude Haiku to check whether a high-margin listing is actually the hardware it
was identified as, or something else (accessory, game, service, bundle without the device).
"""
from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from hardware_scraper.config import get_config
from hardware_scraper.db import make_engine
from hardware_scraper.models import Listing, ListingProduct, Product, Valuation


_PROMPT = """\
A local marketplace listing was classified as a {category}. Check if this is correct.

Title: {title}
Description: {description}

Is this listing selling an actual {category} (working or broken/for-parts)?

Answer KEEP if yes — it is the real device (or broken version of it).
Answer DROP if it is actually an accessory, case, dock, controller, game/software, \
cleaning/repair service, or any non-device item.

Reply with only KEEP or DROP."""


async def run_llm_validate(margin_threshold: float = 300.0) -> None:
    cfg = get_config()
    if not cfg.llm.enabled:
        return

    api_key = cfg.llm.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        return

    from rich.console import Console
    console = Console()
    engine = make_engine(cfg.database.url)

    with Session(engine) as db:
        rows = db.execute(
            select(Listing, Valuation, ListingProduct, Product)
            .join(Valuation, Valuation.listing_id == Listing.id)
            .join(ListingProduct, ListingProduct.listing_id == Listing.id)
            .join(Product, Product.id == ListingProduct.product_id)
            .where(Valuation.margin_pct > margin_threshold)
            .order_by(Valuation.margin_pct.desc())
        ).all()

        if not rows:
            return

        console.print(
            f"[cyan]LLM validating {len(rows)} listings with margin >{margin_threshold:.0f}%...[/cyan]"
        )
        dropped = 0

        for listing, val, lp, product in rows:
            prompt = _PROMPT.format(
                category=product.category,
                title=listing.title,
                description=(listing.description or "").strip()[:500] or "No description",
            )
            try:
                response = client.messages.create(
                    model=cfg.llm.model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": prompt}],
                )
                answer = response.content[0].text.strip().upper()
                if answer.startswith("DROP"):
                    console.print(
                        f"  [red]DROP[/red] ({val.margin_pct:.0f}%) {listing.title[:60]}"
                    )
                    db.delete(val)
                    listing.status = "noise"
                    dropped += 1
                else:
                    console.print(
                        f"  [green]KEEP[/green] ({val.margin_pct:.0f}%) {listing.title[:60]}"
                    )
            except Exception as exc:
                console.print(f"  [yellow]LLM error for listing {listing.id}: {exc}[/yellow]")

        db.commit()

    console.print(f"[green]LLM validation done. Dropped: {dropped} / {len(rows)} checked.[/green]")
