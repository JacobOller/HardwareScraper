from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
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
        return JSONResponse([
            {
                "id": listing.id,
                "title": listing.title,
                "source": listing.source,
                "price": listing.price,
                "category": product.category,
                "condition": lp.condition,
                "ebay_median": val.ebay_median_price,
                "profit": round(val.profit, 2),
                "margin_pct": round(val.margin_pct, 1),
                "margin_tier": val.margin_tier,
                "margin_label": val.margin_label,
                "url": listing.url,
                "comp_count": val.ebay_comp_count,
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
        from hardware_scraper.pipeline.ingest import run_browse, run_ingest
        from hardware_scraper.pipeline.valuate import run_valuate

        cfg = get_config()

        for source in ["offerup", "facebook"]:
            _log(f"Browsing {source}...")
            try:
                await run_browse(source=source)
            except Exception as exc:
                _log(f"Browse {source} error: {exc}")

        for q in cfg.search.queries:
            for source in ["offerup", "facebook"]:
                _log(f"Scraping {source}: {q!r}...")
                try:
                    await run_ingest(query=q, source=source)
                except Exception as exc:
                    _log(f"Scrape {source} {q!r} error: {exc}")

        _log("Valuating...")
        await run_valuate(min_confidence=0.5)
        _log("LLM validating high-margin results...")
        from hardware_scraper.pipeline.validate import run_llm_validate
        await run_llm_validate()
        _log("Scan complete.")

    asyncio.create_task(_run_job(_task()))
    return JSONResponse({"started": True})


@app.post("/api/validate")
async def api_validate(margin_threshold: float = 300.0):
    """Run LLM validation on valuations above margin_threshold%."""
    if _job["running"]:
        return JSONResponse({"error": "A job is already running"}, status_code=409)

    async def _task():
        from hardware_scraper.pipeline.validate import run_llm_validate
        _log(f"LLM validating listings with margin >{margin_threshold:.0f}%...")
        await run_llm_validate(margin_threshold=margin_threshold)
        _log("LLM validation complete.")

    asyncio.create_task(_run_job(_task()))
    return JSONResponse({"started": True})


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
