"""LLM validation pass — drop obvious misrepresentations from high-margin valuations.

Only runs when llm.enabled is true and there are valuations above the margin threshold.
Uses Claude Haiku to check whether a high-margin listing is actually the hardware it
was identified as, or something else (accessory, game, service, bundle without the device).
"""
from __future__ import annotations

import os
from typing import Callable, Optional

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


async def run_llm_validate(
    margin_threshold: Optional[float] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> None:
    def _log(msg: str) -> None:
        print(msg)
        if log_fn:
            log_fn(msg)

    cfg = get_config()
    if margin_threshold is None:
        margin_threshold = cfg.llm.validate_margin_threshold
    if not cfg.llm.enabled:
        _log("LLM validation skipped: llm.enabled is false in config")
        return

    api_key = cfg.llm.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        _log("LLM validation skipped: no API key (set llm.api_key in config.yaml or ANTHROPIC_API_KEY env var)")
        return

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
    except ImportError:
        _log("LLM validation skipped: anthropic package not installed")
        return

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
            _log(f"LLM validation: no listings found with margin >{margin_threshold:.0f}%")
            return

        _log(f"LLM validating {len(rows)} listings with margin >{margin_threshold:.0f}%...")
        dropped = 0

        for listing, val, lp, product in rows:
            prompt = _PROMPT.format(
                category=product.category,
                title=listing.title,
                description=(listing.description or "").strip()[:500] or "No description",
            )
            try:
                response = await client.messages.create(
                    model=cfg.llm.model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": prompt}],
                )
                answer = response.content[0].text.strip().upper()
                if answer.startswith("DROP"):
                    _log(f"DROP ({val.margin_pct:.0f}%) {listing.title[:60]}")
                    db.delete(val)
                    listing.status = "noise"
                    dropped += 1
                else:
                    _log(f"KEEP ({val.margin_pct:.0f}%) {listing.title[:60]}")
            except Exception as exc:
                _log(f"LLM error for listing {listing.id}: {exc}")

        db.commit()

    _log(f"LLM validation done. Dropped {dropped} / {len(rows)} checked.")
