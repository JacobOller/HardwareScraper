from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from hardware_scraper.config import get_config
from hardware_scraper.db import make_engine
from hardware_scraper.models import EbayComp, Listing, ListingProduct, Product, Valuation

app = FastAPI(title="HardwareScraper", docs_url=None, redoc_url=None)

# ---------------------------------------------------------------------------
# Simple in-memory job tracker
# ---------------------------------------------------------------------------

_job: dict = {"running": False, "log": [], "started_at": None}


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    _job["log"].append(f"[{ts}] {msg}")
    if len(_job["log"]) > 200:
        _job["log"] = _job["log"][-200:]


async def _run_job(coro) -> None:
    _job["running"] = True
    _job["log"] = []
    _job["started_at"] = datetime.now().isoformat()
    try:
        await coro
    except Exception as exc:
        _log(f"ERROR: {exc}")
    finally:
        _job["running"] = False


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/results")
def api_results():
    cfg = get_config()
    engine = make_engine(cfg.database.url)
    with Session(engine) as db:
        rows = (
            db.query(Listing, Valuation, ListingProduct, Product)
            .join(Valuation, Valuation.listing_id == Listing.id)
            .join(ListingProduct, ListingProduct.listing_id == Listing.id)
            .join(Product, Product.id == ListingProduct.product_id)
            .order_by(Valuation.margin_pct.desc())
            .all()
        )
        now = datetime.now(timezone.utc)
        return JSONResponse([
            {
                "id": listing.id,
                "title": listing.title,
                "source": listing.source,
                "price": listing.price,
                "category": product.category,
                "condition": lp.condition,
                "ebay_median": val.ebay_median_price,
                "amazon_price": val.amazon_price,
                "profit": round(val.profit, 2),
                "margin_pct": round(val.margin_pct, 1),
                "margin_tier": val.margin_tier,
                "margin_label": val.margin_label,
                "url": listing.url,
                "comp_count": val.ebay_comp_count,
                "saved": listing.saved,
                "hidden": listing.hidden,
                "is_local_pickup": listing.is_local_pickup,
                "inbound_shipping": val.inbound_shipping,
                "working_comp_price": val.working_comp_price,
                "working_comp_count": val.working_comp_count,
                "repair_upside": round(val.working_comp_price - val.ebay_median_price, 2)
                    if val.working_comp_price and val.ebay_median_price else None,
                "days_old": (now - listing.scraped_at.replace(tzinfo=timezone.utc)).days
                    if listing.scraped_at else None,
                "bought_at": listing.bought_at.isoformat() if listing.bought_at else None,
                "bought_price": listing.bought_price,
                "sold_at": listing.sold_at.isoformat() if listing.sold_at else None,
                "sold_price": listing.sold_price,
            }
            for listing, val, lp, product in rows
        ])


@app.get("/api/status")
def api_status():
    return JSONResponse({
        "running": _job["running"],
        "log": _job["log"][-50:],
        "started_at": _job["started_at"],
    })


@app.post("/api/browse")
async def api_browse(source: str = "offerup"):
    if _job["running"]:
        return JSONResponse({"error": "A job is already running"}, status_code=409)

    async def _task():
        from hardware_scraper.pipeline.ingest import run_browse
        _log(f"Browsing {source}...")
        await run_browse(source=source)
        _log("Browse complete.")

    asyncio.create_task(_run_job(_task()))
    return JSONResponse({"started": True})


@app.post("/api/scrape")
async def api_scrape(source: str = "offerup", query: Optional[str] = None):
    if _job["running"]:
        return JSONResponse({"error": "A job is already running"}, status_code=409)

    async def _task():
        from hardware_scraper.pipeline.ingest import run_ingest
        label = f"'{query}'" if query else "default queries"
        _log(f"Scraping {source} for {label}...")
        await run_ingest(query=query, source=source)
        _log("Scrape complete.")

    asyncio.create_task(_run_job(_task()))
    return JSONResponse({"started": True})


@app.post("/api/valuate")
async def api_valuate(min_confidence: float = 0.5):
    if _job["running"]:
        return JSONResponse({"error": "A job is already running"}, status_code=409)

    async def _task():
        from hardware_scraper.pipeline.valuate import run_valuate
        _log("Running valuation...")
        await run_valuate(min_confidence=min_confidence)
        _log("Valuation complete.")

    asyncio.create_task(_run_job(_task()))
    return JSONResponse({"started": True})


@app.post("/api/scan")
async def api_scan():
    """Full pipeline: browse + scrape all top categories + valuate."""
    if _job["running"]:
        return JSONResponse({"error": "A job is already running"}, status_code=409)

    async def _task():
        from hardware_scraper.pipeline.ingest import run_browse, run_ingest, _make_scraper
        from hardware_scraper.pipeline.valuate import run_valuate

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
                _log(f"Browsing {source}...")
                try:
                    await run_browse(source=source, scraper=scraper)
                except Exception as exc:
                    _log(f"Browse {source} error: {exc}")

        async def _scrape_all_queries(source: str) -> None:
            scraper = _make_scraper(cfg, source)
            async with scraper.session():
                for q in cfg.search.queries:
                    _log(f"Scraping {source}: {q!r}...")
                    try:
                        await run_ingest(query=q, source=source, scraper=scraper)
                    except Exception as exc:
                        _log(f"Scrape {source} {q!r} error: {exc}")

        # Browse all sources in parallel
        await asyncio.gather(*[_browse_one(s) for s in browse_and_search])

        # Search all sources in parallel; each source runs its queries with one browser
        await asyncio.gather(*[_scrape_all_queries(s) for s in all_search_sources])

        _log("Valuating...")
        await run_valuate(min_confidence=0.5)
        from hardware_scraper.pipeline.validate import run_llm_validate
        await run_llm_validate(log_fn=_log)
        _log("Scan complete.")

    asyncio.create_task(_run_job(_task()))
    return JSONResponse({"started": True})


@app.post("/api/validate")
async def api_validate(margin_threshold: Optional[float] = None):
    """Run LLM validation on valuations above margin_threshold% (default: config value)."""
    if _job["running"]:
        return JSONResponse({"error": "A job is already running"}, status_code=409)

    async def _task():
        from hardware_scraper.pipeline.validate import run_llm_validate
        await run_llm_validate(margin_threshold=margin_threshold, log_fn=_log)
        _log("LLM validation complete.")

    asyncio.create_task(_run_job(_task()))
    return JSONResponse({"started": True})


@app.post("/api/listings/{listing_id}/save")
def api_save_listing(listing_id: int):
    cfg = get_config()
    engine = make_engine(cfg.database.url)
    with Session(engine) as db:
        listing = db.get(Listing, listing_id)
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        listing.saved = not listing.saved
        db.commit()
        return JSONResponse({"id": listing_id, "saved": listing.saved})


@app.post("/api/listings/{listing_id}/hide")
def api_hide_listing(listing_id: int):
    cfg = get_config()
    engine = make_engine(cfg.database.url)
    with Session(engine) as db:
        listing = db.get(Listing, listing_id)
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        listing.hidden = not listing.hidden
        db.commit()
        return JSONResponse({"id": listing_id, "hidden": listing.hidden})


@app.post("/api/listings/{listing_id}/buy")
def api_buy_listing(listing_id: int, price: Optional[float] = None):
    cfg = get_config()
    engine = make_engine(cfg.database.url)
    with Session(engine) as db:
        listing = db.get(Listing, listing_id)
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        if listing.bought_at:
            # Toggle off (undo buy) only if not yet sold
            if listing.sold_at:
                raise HTTPException(status_code=400, detail="Cannot undo buy after marking sold")
            listing.bought_at = None
            listing.bought_price = None
        else:
            listing.bought_at = datetime.now(timezone.utc)
            listing.bought_price = price if price is not None else listing.price
        db.commit()
        return JSONResponse({
            "id": listing_id,
            "bought_at": listing.bought_at.isoformat() if listing.bought_at else None,
            "bought_price": listing.bought_price,
        })


@app.post("/api/listings/{listing_id}/sell")
def api_sell_listing(listing_id: int, price: float):
    cfg = get_config()
    engine = make_engine(cfg.database.url)
    with Session(engine) as db:
        listing = db.get(Listing, listing_id)
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        if not listing.bought_at:
            raise HTTPException(status_code=400, detail="Mark as bought before marking sold")
        if listing.sold_at:
            # Toggle off (undo sell)
            listing.sold_at = None
            listing.sold_price = None
        else:
            listing.sold_at = datetime.now(timezone.utc)
            listing.sold_price = price
        db.commit()
        return JSONResponse({
            "id": listing_id,
            "sold_at": listing.sold_at.isoformat() if listing.sold_at else None,
            "sold_price": listing.sold_price,
        })


@app.delete("/api/reset")
def api_reset():
    """Delete all listings, products, valuations, and eBay comps from the DB."""
    if _job["running"]:
        return JSONResponse({"error": "A job is already running"}, status_code=409)
    cfg = get_config()
    engine = make_engine(cfg.database.url)
    with Session(engine) as db:
        deleted = db.query(Listing).count()
        db.query(Valuation).delete()
        db.query(EbayComp).delete()
        db.query(ListingProduct).delete()
        db.query(Listing).delete()
        db.query(Product).delete()
        db.commit()
    return JSONResponse({"deleted": deleted})


# ---------------------------------------------------------------------------
# Dashboard HTML
# ---------------------------------------------------------------------------

_HTML = Path(__file__).parent / "dashboard.html"


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(_HTML.read_text(encoding="utf-8"))
