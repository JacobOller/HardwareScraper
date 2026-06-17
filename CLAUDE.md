# HardwareScraper — Claude Reference

## What This Project Does

Finds underpriced PC hardware on local marketplace platforms (OfferUp, Facebook Marketplace), estimates resale value via eBay sold listings, and ranks opportunities by profit margin. Personal use, runs locally.

## Current Phase

Phase 2A complete. Phase 2B (automation/Discord) next. See `plan.md` for full roadmap.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.14 (venv at `.venv/`) |
| Browser automation | Playwright (headless, persistent session) + playwright-stealth |
| eBay data | Playwright scraping (eBay API registration blocked by Cloudflare) |
| Database | SQLite (`data/hardware_scraper.db`) |
| ORM / migrations | SQLAlchemy 2.0 + Alembic |
| Scheduling | APScheduler (installed, not yet wired up) |
| CLI | Typer (`hardware-scraper` command) |
| Config | YAML + pydantic-settings (`config.yaml`) |
| Output | Rich (terminal tables) + CSV |
| HTML parsing | BeautifulSoup4 |
| LLM fallback | Anthropic SDK — `claude-haiku-4-5`, gated by `llm.enabled` in config |

## Project Structure (actual, as-built)

```
HardwareScraper/
├── CLAUDE.md
├── plan.md
├── pyproject.toml
├── config.yaml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/4ed4e0f3987b_initial_schema.py
├── src/hardware_scraper/
│   ├── cli.py                    # Typer app: scrape, browse, fb-scrape, fb-browse, valuate, report, db-upgrade
│   ├── config.py                 # YAML → pydantic, singleton get_config()
│   ├── models/
│   │   ├── base.py               # DeclarativeBase
│   │   ├── listing.py            # Listing model
│   │   ├── product.py            # Product + ListingProduct models
│   │   └── valuation.py          # EbayComp + Valuation models
│   ├── scrapers/
│   │   ├── base.py               # RawListing dataclass, BaseScraper ABC
│   │   ├── offerup.py            # OfferUp scraper (Playwright, persistent session)
│   │   └── facebook.py           # Facebook Marketplace scraper (Playwright, persistent session)
│   ├── parsers/
│   │   ├── category_rules.py     # Regex patterns for categories, brands, models; is_refurb_noise()
│   │   ├── title_parser.py       # TitleParser → ParsedTitle with confidence score
│   │   └── llm_parser.py         # LLMParser → Claude Haiku fallback for low-confidence titles
│   ├── ebay/
│   │   ├── client.py             # EbayClient (OAuth API — unused, no credentials)
│   │   ├── comp_fetcher.py       # CompFetcher: routes to API or scraper fallback
│   │   └── scraper.py            # EbayScraper (Playwright + stealth, active path)
│   ├── valuation/
│   │   └── calculator.py         # ValuationCalculator → margin formula + per-category shipping
│   ├── pipeline/
│   │   ├── ingest.py             # run_ingest() + run_browse(): scrape → filter → parse → store
│   │   └── valuate.py            # run_valuate(): fetch comps → calculate margins
│   └── output/
│       └── reporter.py           # Rich table + CSV export
├── data/                         # gitignored: *.db, browser_session/, facebook_session/, ebay_session/, exports/
├── scripts/
│   ├── debug_offerup.py          # dev diagnostic
│   ├── debug_ebay.py             # dev diagnostic
│   ├── debug_category.py         # dev diagnostic for OfferUp category pages
│   ├── debug_urls.py             # dev diagnostic for listing URL format
│   ├── check_db.py               # full DB dump with all valuations
│   ├── check_listings.py         # listing status breakdown
│   └── reset_valuations.py       # clear comps+valuations for re-run
└── tests/
    ├── test_title_parser.py      # 17 tests
    └── test_valuation_calculator.py  # 5 tests
```

## Key Data Models

**`listings`** — raw marketplace data (source, external_id, url, title, price, location, description, image_urls, posted_at, scraped_at, status)

**`products`** — normalized hardware identity (category, brand, model, specs JSON, canonical_name used as eBay search key)

**`listing_products`** — many-to-one link with confidence score and condition

**`ebay_comps`** — cached sold data (product_id, sold_price, shipping, condition, sold_date, ebay_item_id, fetched_at)

**`valuations`** — computed margins (ebay_median_price, ebay_comp_count, estimated_fees, estimated_shipping, net_resale, profit, margin_pct, margin_tier, margin_label)

## Margin Formula

```
net_resale  = median_ebay_sold_price - (median_ebay * 0.1325 + 0.30) - outbound_shipping
profit      = net_resale - asking_price
margin_pct  = (profit / asking_price) * 100
```

Outbound shipping is per-category from `config.yaml` `shipping.by_category` (e.g. cpu $8, desktop $40). Falls back to `shipping.default` ($15) if category not in the table.

## Margin Tiers

| Tier | Margin % | Label |
|------|----------|-------|
| 1 | ≥ 50% | Excellent |
| 2 | 30–49% | Good |
| 3 | 15–29% | Marginal |
| 4 | 0–14% | Low |
| 5 | < 0% | Overpriced |

## Design Rules

- **Modular scrapers** — each marketplace is a pluggable adapter behind a common `RawListing` interface
- **Scrape then analyze** — raw listings stored first; valuation is a separate pass so eBay lookups can be batched/retried
- **Idempotent** — re-running never creates duplicate records (dedup by `source` + `external_id`)
- **Config over code** — all tunable values in `config.yaml`, not code

## How the OfferUp Scraper Works

- Playwright persistent context at `data/browser_session/` (stores login cookies)
- `search(query)` — hits `/search/?q={query}&radius=&zipcode=` with keyword
- `browse()` — hits `/search/?q=&radius=&zipcode=` (empty query) to surface ALL local listings; OfferUp ignores category_id URL params and `/cat/` pages contain no listing data
- Primary extraction: `props.pageProps.searchFeedResponse.looseTiles` from `__NEXT_DATA__` JSON
- Filters tiles where `tileType == "LISTING"`
- Falls back to DOM scraping if `__NEXT_DATA__` structure changes
- Uses `wait_until="domcontentloaded"` — OfferUp never reaches networkidle

## How the Facebook Marketplace Scraper Works

- Playwright persistent context at `data/facebook_session/`
- First-time setup: set `facebook.headless: false` in config.yaml, run `hardware-scraper fb-browse`, log in manually, then set `headless: true`
- `search(query)` — hits `facebook.com/marketplace/search/?query={query}&exact=false`
- `browse()` — hits `facebook.com/marketplace/local/`
- Primary extraction: scans all `<script type="application/json">` Relay store blobs for objects containing `marketplace_listing_title` + `listing_price`
- Falls back to DOM card scraping via `a[href*="/marketplace/item/"]` links
- Scrolls incrementally to load more items; stops early if no new IDs appear after 3 scroll rounds
- Uses `wait_until="domcontentloaded"` + rate_limit_seconds sleep between scrolls

## How the eBay Scraper Works

- No API credentials — eBay Developer Program registration blocked by Cloudflare for this user
- Uses `EbayScraper` in `ebay/scraper.py` — Playwright + `playwright-stealth` + persistent session at `data/ebay_session/`
- URL: `ebay.com/sch/i.html?LH_Sold=1&LH_Complete=1` for sold/completed listings
- `wait_until="domcontentloaded"` + 3s wait (eBay never reaches networkidle)
- Item selector: `.srp-results li` filtered for `s-card` class (eBay redesigned from `li.s-item` in 2024)
- Price: `span.s-card__price` — skips `strikethrough` class (best-offer-accepted, actual price hidden)
- Sold date: `div.s-card__caption`
- Item ID: `data-listingid` attribute
- `CompFetcher` auto-routes: uses `EbayClient` if `app_id`/`cert_id` set, else falls back to `EbayScraper`

## Product Identification Pipeline

1. Refurb noise filter — `is_refurb_noise(title)` drops `SHOP\d+` / `INV.\d+` patterns before DB write
2. Category detection — **system categories (desktop, laptop) checked first**, then components; prevents "Gaming PC with RTX 2060" → gpu misidentification
3. Brand/model extraction:
   - GPU: `RTX \d{4}`, `GTX \d{4}`, `RX \d{4}` patterns
   - CPU: `i[3579]-\d{4,5}`, Ryzen patterns
   - Laptop: brand (Lenovo/Dell/HP/Apple/ASUS/etc.) + specific model (ThinkPad T460, MacBook Pro M1, EliteBook 840 G8, XPS 15, etc.)
   - Desktop: GPU or CPU extracted for system-level eBay search (canonical = "Gaming PC RTX 3080")
4. Spec extraction (VRAM GB, RAM GB)
5. Condition inference ("for parts", "like new", "used")
6. Confidence score: 0.3 (category) + 0.2 (brand) + 0.4 (model) + 0.1 (explicit condition)
7. If confidence < `llm.confidence_threshold` (default 0.5) and `llm.enabled: true`, falls back to `LLMParser`
8. Listings with final confidence < 0.5 are stored as `status=new` but not valuated

Canonical name examples: `"NVIDIA RTX 3080 10GB"`, `"AMD Ryzen 7 5800X"`, `"Lenovo ThinkPad T460"`, `"Gaming PC RTX 2060"`

## LLM Fallback

- Model: `claude-haiku-4-5` (cheapest, fast, ~$0.001/listing)
- Gated by `llm.enabled: true` in config.yaml
- API key: `llm.api_key` in config.yaml or `ANTHROPIC_API_KEY` env var
- Returns same `ParsedTitle` dataclass as regex parser
- Only called when regex confidence < `llm.confidence_threshold` (default 0.5)

## CLI Commands

```powershell
# Always activate venv first
.venv\Scripts\Activate.ps1

# OfferUp
hardware-scraper scrape --query "RTX 3080"        # scrape OfferUp by keyword
hardware-scraper browse                            # fetch all local OfferUp listings

# Facebook Marketplace
hardware-scraper fb-scrape --query "RTX 3080"     # search FB Marketplace by keyword
hardware-scraper fb-browse                         # fetch all local FB listings
# (also works as: hardware-scraper scrape --source facebook, browse --source facebook)

# Valuation & reporting
hardware-scraper valuate                           # fetch eBay comps, calculate margins
hardware-scraper valuate --min-confidence 0.5      # include LLM-identified listings
hardware-scraper report                            # show ranked results (Rich table)
hardware-scraper report --csv                      # also save to data/exports/
hardware-scraper db-upgrade                        # apply Alembic migrations
```

## config.yaml Key Values

```yaml
scraping:
  location_zip: "02766"
  radius_miles: 40             # covers Lowell MA → past Providence RI
  headless: true               # false for first OfferUp login, true after
  rate_limit_seconds: 3.0

facebook:
  session_dir: "data/facebook_session"
  headless: false              # false for first FB login, true after
  enabled: true

shipping:
  default: 15.00
  by_category:
    cpu: 8.00
    ram: 6.00
    ssd: 7.00
    hdd: 10.00
    gpu: 15.00
    motherboard: 12.00
    psu: 12.00
    cooling: 10.00
    case: 30.00
    laptop: 15.00
    desktop: 40.00

ebay:
  app_id: ""                   # empty = use scraper fallback
  cert_id: ""

llm:
  enabled: true                # Claude Haiku fallback for low-confidence titles
  api_key: ""                  # or set ANTHROPIC_API_KEY env var
  model: "claude-haiku-4-5"
  confidence_threshold: 0.5

output:
  min_margin_to_show: -9999    # show all; raise to filter (e.g. 15 = Marginal+)
```

## Known Issues / Gotchas

- **Facebook login required** — first run must use `facebook.headless: false` to log in manually; session persists after that.
- **eBay HTML changes frequently** — selectors in `ebay/scraper.py` may need updating. Run `scripts/debug_ebay.py` to diagnose.
- **OfferUp `__NEXT_DATA__` path** changed once already. Legacy path kept as fallback in `_extract_listings`.
- **All comps cached per (product_id, condition) for 24h** — run `scripts/reset_valuations.py` to force fresh fetch.
- **OfferUp listing URLs** use UUID format: `https://offerup.com/item/detail/{uuid}` — links go dead quickly when sellers remove listings.
- **Desktop confidence = 0.7** — desktop listings with a GPU identified get confidence 0.7 (category + model), which clears the 0.5 valuation threshold but may still miss some edge cases without LLM.
