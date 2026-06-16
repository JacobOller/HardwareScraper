# HardwareScraper — Claude Reference

## What This Project Does

Finds underpriced PC hardware on local marketplace platforms (OfferUp, Facebook Marketplace), estimates resale value via eBay sold listings, and ranks opportunities by profit margin. Personal use, runs locally.

## Current Phase

Phase 1 — proof of concept. No code yet. See [plan.md](plan.md) for full detail.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.12+ |
| Browser automation | Playwright (headless, persistent session) |
| HTTP client | httpx (async) |
| eBay integration | Official eBay Developer API (Browse/Finding API) |
| Database | SQLite → PostgreSQL when scaling |
| ORM / migrations | SQLAlchemy + Alembic |
| Scheduling | APScheduler |
| CLI | Typer |
| Config | YAML + pydantic-settings (`config.yaml`) |
| Output | Rich (terminal tables) + CSV |
| Optional UI (Phase 3) | Streamlit or FastAPI + React |

## Project Structure (target layout)

```
HardwareScraper/
├── plan.md
├── CLAUDE.md
├── pyproject.toml
├── config.yaml
├── src/hardware_scraper/
│   ├── cli.py
│   ├── config.py
│   ├── models/          # listing.py, product.py, valuation.py
│   ├── scrapers/        # base.py, offerup.py, facebook.py (Phase 2)
│   ├── parsers/         # title_parser.py, category_rules.py
│   ├── ebay/            # client.py, comp_fetcher.py, outlier_filter.py
│   ├── valuation/       # calculator.py, tier_classifier.py
│   ├── pipeline/        # ingest.py, identify.py, valuate.py
│   └── output/          # reporter.py, formatter.py
├── data/                # hardware_scraper.db (gitignored)
├── tests/
└── scripts/             # seed_product_db.py
```

## Key Data Models

**`listings`** — raw marketplace data (source, external_id, url, title, price, location, description, image_urls, posted_at, scraped_at, status)

**`products`** — normalized hardware identity (category, brand, model, specs JSON, canonical_name used as eBay search key)

**`listing_products`** — many-to-one link with confidence score

**`ebay_comps`** — cached sold data (product_id, sold_price, shipping, condition, sold_date, ebay_item_id)

**`valuations`** — computed margins (ebay_median_price, ebay_comp_count, estimated_fees, estimated_shipping, net_resale, profit, margin_pct, margin_tier)

## Margin Formula

```
net_resale  = median_ebay_sold_price - ebay_fees - outbound_shipping
profit      = net_resale - asking_price
margin_pct  = (profit / asking_price) * 100
```

Default fees: 13.25% eBay rate + $0.30/order. All fee/shipping values live in `config.yaml`, not code.

## Margin Tiers

| Tier | Margin % | Label |
|------|----------|-------|
| 1 | ≥ 50% | Excellent |
| 2 | 30–49% | Good |
| 3 | 15–29% | Marginal |
| 4 | 0–14% | Low |
| 5 | < 0% | Overpriced |

Thresholds are configurable in `config.yaml`.

## Design Rules

- **Modular scrapers** — each marketplace is a pluggable adapter behind a common `Listing` interface
- **Scrape then analyze** — raw listings stored first; valuation is a separate pass so eBay lookups can be batched/retried
- **Idempotent** — re-running never creates duplicate records (dedup by `source` + `external_id`)
- **Config over code** — search terms, location, margin thresholds, fee rates, shipping estimates all go in `config.yaml`

## Product Identification Pipeline

1. Category detection via keyword rules
2. Brand/model extraction via regex + lookup tables (e.g., `RTX \d{4}`, `i[3579]-\d{4,5}`)
3. Spec extraction (RAM, storage, VRAM)
4. Condition inference ("for parts", "like new")
5. Confidence score (0–1); low-confidence listings flagged for review, not auto-valuated

eBay comps: fetch last 60 days of sold listings, remove IQR outliers, take **median** sold price. Cache by `(canonical_name, condition)` for 24 hours.

## Sources

- **OfferUp** — Phase 1. Playwright headless with persistent session.
- **Facebook Marketplace** — Phase 2+. ToS risk; consider manual CSV import as interim.
- **eBay** — prefer official API. Unofficial scraping only as fallback.

> Scraping OfferUp/Facebook may violate their ToS. This tool is for personal local use with conservative rate limiting.

## CLI Commands (target)

```
hardware-scraper scrape --query "RTX 3070"
hardware-scraper valuate
hardware-scraper report
```

## Open Questions (unresolved)

1. Single zip code or multiple cities?
2. Facebook: full scraper vs. manual CSV import?
3. Factor in gas/travel as acquisition cost?
4. How strictly to filter "for parts" condition in comps?
5. Notifications: real-time or daily digest?
6. Deployment: local-only or hosted 24/7?

## Next Steps

1. Register for eBay Developer Program and get API credentials
2. Scaffold project (`pyproject.toml`, config, CLI skeleton)
3. Build SQLite schema + Alembic migrations
4. Build OfferUp scraper proof of concept
5. Collect 50–100 real titles to tune title parser before writing valuation logic
