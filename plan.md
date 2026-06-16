# HardwareScraper — Project Plan

## 1. Vision

Build a tool that continuously discovers underpriced electronics on local marketplace platforms (OfferUp, Facebook Marketplace), estimates their resale value using eBay **sold** listings, and surfaces opportunities ranked by **profit margin** after fees and estimated costs.

**Target categories (initial):** laptops, desktops, CPUs, GPUs, RAM, SSDs, monitors, and related PC components.

**Success criteria:**
- Reliably ingest new listings within minutes of posting (or on a configurable schedule)
- Match marketplace listings to comparable eBay sold data with reasonable accuracy
- Produce a clear, sortable view of deals grouped by margin tier (e.g., excellent / good / marginal / skip)
- Run locally with minimal manual intervention

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Scheduler / CLI                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  OfferUp        │ │  FB Marketplace │ │  (Future:       │
│  Scraper        │ │  Scraper        │ │   Craigslist)   │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
                  ┌─────────────────────┐
                  │  Listing Normalizer │
                  │  + Deduplicator     │
                  └──────────┬──────────┘
                             ▼
                  ┌─────────────────────┐
                  │  Product Identifier │
                  │  (title → model)    │
                  └──────────┬──────────┘
                             ▼
                  ┌─────────────────────┐
                  │  eBay Sold Lookup   │
                  └──────────┬──────────┘
                             ▼
                  ┌─────────────────────┐
                  │  Margin Calculator  │
                  └──────────┬──────────┘
                             ▼
                  ┌─────────────────────┐
                  │  SQLite / Postgres  │
                  └──────────┬──────────┘
                             ▼
                  ┌─────────────────────┐
                  │  Output Layer       │
                  │  (CLI table, CSV,   │
                  │   optional web UI)  │
                  └─────────────────────┘
```

**Design principles:**
- **Modular scrapers** — each marketplace is a pluggable adapter behind a common `Listing` interface
- **Separation of scrape vs. analyze** — raw listings are stored first; valuation runs as a second pass so eBay lookups can be batched and retried
- **Idempotent pipelines** — re-running should not create duplicate records
- **Configurable** — search terms, location radius, margin thresholds, and fee assumptions live in config, not code

---

## 3. Data Sources & Scraping Strategy

### 3.1 OfferUp

| Aspect | Notes |
|--------|-------|
| Access | Web app; may require session cookies or Playwright-based browser automation |
| Data available | Title, price, location, photos, description, posted date |
| Challenges | Anti-bot measures, dynamic loading, login walls for some features |
| Recommended approach | Playwright headless browser with persistent session; respect rate limits |

### 3.2 Facebook Marketplace

| Aspect | Notes |
|--------|-------|
| Access | Heavily login-gated; unofficial scraping is fragile and against ToS |
| Data available | Title, price, location, images, seller info |
| Challenges | Frequent DOM changes, account risk, CAPTCHAs, legal/ToS concerns |
| Recommended approach | **Phase 2+** — treat as optional. Consider manual CSV import or browser extension as a safer interim path |

### 3.3 eBay Sold Listings

| Aspect | Notes |
|--------|-------|
| Access | Official [eBay Browse API](https://developer.ebay.com/api-docs/buy/browse/overview.html) or [Finding API](https://developer.ebay.com/devzone/finding/CallRef/index.html) for completed/sold items; unofficial scraping as fallback |
| Data needed | Sold price, condition, shipping, end date, title |
| Challenges | Matching vague marketplace titles to the right eBay comps; filtering outliers |
| Recommended approach | **Prefer official API** (free tier with registration). Cache results aggressively. Use median of recent sold prices, not single listings |

### 3.4 Scraping Risk Summary

> **Important:** Automated scraping of OfferUp and Facebook may violate their Terms of Service. eBay provides official APIs that should be preferred. This project should be built for **personal, local use** with conservative rate limiting. Document risks and let the user decide scope.

---

## 4. Core Data Model

### `listings` (raw marketplace data)
| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `source` | enum | `offerup`, `facebook`, etc. |
| `external_id` | string | Platform-specific listing ID |
| `url` | string | Link to original listing |
| `title` | string | Raw title |
| `price` | decimal | Asking price |
| `location` | string | City / zip |
| `description` | text | Full description if available |
| `image_urls` | json | Array of image URLs |
| `posted_at` | datetime | When listed |
| `scraped_at` | datetime | When we ingested it |
| `status` | enum | `active`, `sold`, `expired`, `ignored` |

### `products` (normalized hardware identity)
| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `category` | enum | `laptop`, `desktop`, `gpu`, `cpu`, etc. |
| `brand` | string | e.g., NVIDIA, AMD, Dell |
| `model` | string | e.g., RTX 3070, i7-12700K |
| `specs` | json | Parsed specs (VRAM, RAM, storage, etc.) |
| `canonical_name` | string | Normalized search key for eBay |

### `listing_products` (many-to-one link)
Links a listing to its best-guess product match with a confidence score.

### `ebay_comps` (cached sold data)
| Field | Type | Description |
|-------|------|-------------|
| `product_id` | UUID | FK to products |
| `sold_price` | decimal | Final sold price |
| `shipping` | decimal | Shipping cost |
| `condition` | string | eBay condition label |
| `sold_date` | date | When it sold |
| `title` | string | Original eBay title |
| `ebay_item_id` | string | For dedup |

### `valuations` (computed margins)
| Field | Type | Description |
|-------|------|-------------|
| `listing_id` | UUID | FK |
| `ebay_median_price` | decimal | Median of recent comps |
| `ebay_comp_count` | int | Number of comps used |
| `estimated_fees` | decimal | eBay + payment fees |
| `estimated_shipping` | decimal | Cost to ship item |
| `net_resale` | decimal | After fees and shipping |
| `profit` | decimal | `net_resale - asking_price` |
| `margin_pct` | decimal | `profit / asking_price * 100` |
| `margin_tier` | enum | See Section 6 |
| `computed_at` | datetime | Timestamp |

---

## 5. Product Identification Pipeline

Marketplace titles are messy. A dedicated parsing step is critical.

### 5.1 Title Parsing Stages

1. **Category detection** — keyword rules + optional lightweight classifier (`gpu`, `laptop`, `cpu`, etc.)
2. **Brand / model extraction** — regex + lookup tables for common hardware (e.g., `RTX \d{4}`, `i[3579]-\d{4,5}[A-Z]*`, `Ryzen \d`)
3. **Spec extraction** — RAM (16GB), storage (512GB SSD), VRAM (8GB)
4. **Condition inference** — "broken", "for parts", "like new" affects comp filtering
5. **Confidence score** — 0–1; skip or flag low-confidence matches

### 5.2 eBay Comp Matching

For each identified product:
1. Build search query from `canonical_name` + condition filter
2. Fetch last N sold listings (e.g., 30–90 days, min 5 results)
3. Remove outliers (IQR or ±2 std dev from median)
4. Compute **median sold price** and **median shipping**
5. Cache by `(canonical_name, condition)` for 24–48 hours

### 5.3 Handling Ambiguity

| Scenario | Strategy |
|----------|----------|
| Title says "gaming PC" with no GPU model | Use category average or flag as `needs_review` |
| Bundle (PC + monitor) | Try to split or exclude from auto-valuation |
| "OBO" / missing price | Store as null; exclude from margin calc |
| Parts / broken | Filter eBay comps to "For parts" condition only |

---

## 6. Profit Margin Calculation

### 6.1 Formula

```
gross_resale     = median_ebay_sold_price
ebay_fees        = gross_resale * fee_rate + per_order_fee
payment_fees     = gross_resale * payment_rate   # often bundled in eBay fees
outbound_ship    = estimated_shipping_cost
net_resale       = gross_resale - ebay_fees - outbound_ship
profit           = net_resale - asking_price - acquisition_costs
margin_pct       = (profit / asking_price) * 100
```

### 6.2 Default Assumptions (configurable)

| Parameter | Default | Notes |
|-----------|---------|-------|
| eBay fee rate | ~13.25% | Varies by category; make configurable per category |
| Per-order fee | $0.30 | |
| Outbound shipping | Category-based flat rate | e.g., GPU=$15, desktop=$40, laptop=$20 |
| Acquisition cost | $0 | Optional: gas, meeting time, PayPal transfer fees |
| Comp window | 60 days | How far back to look for sold items |
| Min comp count | 5 | Below this, mark as `low_confidence` |

### 6.3 Margin Tiers (grouping)

| Tier | Margin % | Label | Action |
|------|----------|-------|--------|
| 1 | ≥ 50% | **Excellent** | High priority — investigate immediately |
| 2 | 30–49% | **Good** | Worth pursuing |
| 3 | 15–29% | **Marginal** | Only if local/easy pickup |
| 4 | 0–14% | **Low** | Probably skip |
| 5 | < 0% | **Overpriced** | Ignore |

Tiers should be configurable in `config.yaml`.

---

## 7. Recommended Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | **Python 3.12+** | Rich scraping ecosystem (Playwright, BeautifulSoup, httpx) |
| Browser automation | **Playwright** | Reliable for JS-heavy sites (OfferUp, FB) |
| HTTP client | **httpx** | Async-friendly for API calls |
| eBay integration | **eBay Developer API** | Official, stable, ToS-compliant |
| Database | **SQLite** (start) → **PostgreSQL** (scale) | Zero-config locally; migrate if multi-user |
| ORM | **SQLAlchemy** or raw SQL with migrations via **Alembic** |
| Task scheduling | **APScheduler** or cron | Periodic scrape + valuation runs |
| CLI | **Typer** or **Click** | `scrape`, `valuate`, `report` commands |
| Config | **YAML** + **pydantic-settings** | Type-safe, human-readable |
| Output | **Rich** (terminal tables) + CSV export | Quick visual scanning |
| Optional UI | **FastAPI + simple React** or **Streamlit** | Phase 3 |

---

## 8. Project Structure

```
HardwareScraper/
├── plan.md
├── README.md
├── pyproject.toml
├── config.yaml
├── src/
│   └── hardware_scraper/
│       ├── __init__.py
│       ├── cli.py                  # Entry point
│       ├── config.py               # Settings loader
│       ├── models/                 # SQLAlchemy models
│       │   ├── listing.py
│       │   ├── product.py
│       │   └── valuation.py
│       ├── scrapers/
│       │   ├── base.py             # Abstract scraper interface
│       │   ├── offerup.py
│       │   └── facebook.py         # Phase 2
│       ├── parsers/
│       │   ├── title_parser.py     # Extract brand/model/specs
│       │   └── category_rules.py   # Keyword → category maps
│       ├── ebay/
│       │   ├── client.py           # API wrapper
│       │   ├── comp_fetcher.py     # Sold listing retrieval
│       │   └── outlier_filter.py
│       ├── valuation/
│       │   ├── calculator.py       # Margin math
│       │   └── tier_classifier.py
│       ├── pipeline/
│       │   ├── ingest.py           # Scrape → DB
│       │   ├── identify.py         # Listing → product
│       │   └── valuate.py          # Product → margin
│       └── output/
│           ├── reporter.py         # CLI tables, CSV
│           └── formatter.py
├── data/
│   └── hardware_scraper.db         # SQLite (gitignored)
├── tests/
│   ├── test_title_parser.py
│   ├── test_margin_calculator.py
│   └── fixtures/                   # Sample HTML/JSON
└── scripts/
    └── seed_product_db.py          # GPU/CPU model lookup tables
```

---

## 9. Implementation Phases

### Phase 1 — Foundation (Week 1–2)
**Goal:** End-to-end proof of concept with one source and manual eBay lookup.

- [ ] Project scaffolding (pyproject.toml, config, CLI skeleton)
- [ ] SQLite schema + migrations
- [ ] `Listing` data model and base scraper interface
- [ ] OfferUp scraper (single search term, single location)
- [ ] Basic title parser (GPU and laptop patterns)
- [ ] eBay sold comp fetcher via official API
- [ ] Margin calculator with tier classification
- [ ] CLI `report` command showing ranked deals

**Deliverable:** Run `hardware-scraper scrape --query "RTX 3070"` and get a margin-ranked table.

### Phase 2 — Robustness (Week 3–4)
**Goal:** Production-quality parsing, dedup, and scheduling.

- [ ] Expand title parser to CPUs, desktops, RAM, SSDs
- [ ] Product lookup tables (common GPU/CPU model names)
- [ ] Deduplication (same listing scraped twice)
- [ ] eBay comp caching and outlier filtering
- [ ] Configurable search profiles (multiple queries, radii)
- [ ] APScheduler for periodic runs
- [ ] CSV export
- [ ] Logging and error alerting

**Deliverable:** Unattended daily scans with reliable output.

### Phase 3 — Facebook & UX (Week 5–6)
**Goal:** Second marketplace + better visibility.

- [ ] Facebook Marketplace scraper (or CSV import fallback)
- [ ] Optional Streamlit/FastAPI dashboard
- [ ] Image thumbnail display in reports
- [ ] "Hide seen" / bookmark / notes on listings
- [ ] Notification hook (Discord webhook or email) for Excellent-tier deals

**Deliverable:** Multi-source dashboard with alerts.

### Phase 4 — Intelligence (Future)
**Goal:** Smarter matching and fewer false positives.

- [ ] ML-based title classification (optional)
- [ ] Image recognition for GPU/laptop model ID
- [ ] Historical price tracking and trend charts
- [ ] Craigslist integration
- [ ] PostgreSQL migration for multi-machine deployment

---

## 10. Configuration Example

```yaml
location:
  zip: "90210"
  radius_miles: 25

searches:
  - query: "RTX 3070"
    category: gpu
  - query: "gaming laptop"
    category: laptop
  - query: "i7 desktop"
    category: desktop
  - query: "Ryzen 5"
    category: cpu

scrape:
  interval_minutes: 30
  max_listings_per_query: 50

ebay:
  comp_days: 60
  min_comp_count: 5
  cache_hours: 24

fees:
  ebay_rate: 0.1325
  per_order: 0.30

shipping_estimates:
  gpu: 15
  laptop: 20
  desktop: 40
  cpu: 10
  default: 15

margins:
  excellent: 50
  good: 30
  marginal: 15

sources:
  offerup:
    enabled: true
  facebook:
    enabled: false
```

---

## 11. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Marketplace ToS violations | Account ban, legal exposure | Personal use only; rate limit; prefer APIs; document risks |
| Facebook scraping fragility | Unreliable data | Defer to Phase 3; offer manual import |
| Bad title → wrong eBay comp | False profit signals | Confidence scores; min comp count; manual review flag |
| eBay API rate limits | Missed valuations | Aggressive caching; batch requests |
| Outlier sold prices | Skewed medians | IQR filtering; condition matching |
| Stale listings | Wasted effort | Track listing age; mark expired after N days |
| Local pickup only items | Shipping estimate irrelevant | Detect "local only" in description; adjust calc |

---

## 12. Testing Strategy

| Area | Approach |
|------|----------|
| Title parser | Unit tests with real-world title fixtures (messy strings from Reddit, Slickdeals, etc.) |
| Margin calculator | Pure function tests with known inputs/outputs |
| eBay client | Mock API responses; one integration test with real API (skipped in CI) |
| Scrapers | Recorded HTML fixtures (VCR-style); no live scraping in CI |
| Pipeline | End-to-end test with seeded DB data |

---

## 13. Open Questions

1. **Geographic scope** — Single zip code or multiple cities?
2. **Facebook approach** — Full scraper vs. browser extension vs. manual CSV import?
3. **Acquisition costs** — Factor in gas/travel time, or pure flip math?
4. **Condition matching** — How strictly should "for parts" listings be filtered?
5. **Notification urgency** — Real-time alerts or daily digest?
6. **Deployment** — Local-only, or hosted service running 24/7?

---

## 14. Next Steps

1. **Answer open questions** in Section 13 to finalize scope
2. **Register for eBay Developer Program** and obtain API credentials
3. **Begin Phase 1** — scaffold project and build OfferUp scraper proof of concept
4. **Collect sample listings** — scrape 50–100 real titles to tune the title parser before building valuation logic

---

*Last updated: 2026-06-15*
