# HardwareScraper — Claude Reference

## What This Project Does

Finds underpriced PC hardware on local marketplace platforms (OfferUp, Facebook Marketplace), estimates resale value via eBay sold listings, and ranks opportunities by profit margin. Personal use, runs locally.

## Current Phase

Phases 2A–2G complete. Phase 2B (automation/Discord) next. See `plan.md` for full roadmap.

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
│   │   ├── valuate.py            # run_valuate(): fetch comps → calculate margins
│   │   └── validate.py           # run_llm_validate(): LLM-check high-margin listings for misrepresentations
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

eBay sold listings are used for **price discovery only**. Fees reflect **Amazon FBM (individual seller)** since that is the resale platform.

```
net_resale  = median_ebay_sold_price - (median_ebay * 0.08 + 0.99) - outbound_shipping
profit      = net_resale - asking_price
margin_pct  = (profit / asking_price) * 100
```

Fee breakdown: `0.08` = Amazon 8% electronics referral rate, `0.99` = individual seller per-item fee. Outbound shipping is per-category from `config.yaml` `shipping.by_category` (e.g. cpu $8, desktop $40). Falls back to `shipping.default` ($15) if category not in the table.

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
- **Session reuse**: `run_valuate()` opens one shared `EbayScraper.session()` context for the entire valuation run. All `fetch_and_cache` calls reuse it — one browser launch total instead of one per product. Cuts valuate time from ~20 min → ~3-5 min for 300 listings.

## Product Identification Pipeline

1. Refurb noise filter — `is_refurb_noise(title)` drops `SHOP\d+` / `INV.\d+` patterns before DB write
2. **Accessory noise filter** — `is_accessory_noise(title)` drops phone cases, console games/controllers, docks, cleaning services, storage enclosures (47+ regex patterns) before DB write
3. **$0 price filter** — listings with `price is None or price <= 0` dropped before DB write
3. Category detection — **priority order: console > phone > desktop > laptop > components**; prevents "Gaming PC with RTX 2060" → gpu misidentification, "PS5 gaming console" → desktop
4. Brand/model extraction:
   - GPU: `RTX \d{4}`, `GTX \d{4}`, `RX \d{4}` patterns
   - CPU: `i[3579]-\d{4,5}`, Ryzen patterns
   - Laptop: brand + specific model; MacBook captures screen size + chip variant + year (`"Apple MacBook Pro 14 M3 Pro 2023"`)
   - Desktop: GPU or CPU extracted for system-level eBay search (canonical = "Gaming PC RTX 3080")
   - **Console**: brand (Sony/Microsoft/Nintendo/Valve) + model (PS5/Xbox Series X/Switch OLED/Steam Deck)
   - **Phone**: brand (Apple/Samsung/Google) + model (iPhone 15 Pro Max / Galaxy S23 Ultra)
5. Spec extraction (VRAM GB, RAM GB, storage GB for phones)
6. Condition inference — 20+ patterns including: "for parts", "not working", "broken", "no display", "cracked screen", "bent pins", "water damage", "bios only", "no post", "won't power on", etc.
7. Confidence score: 0.3 (category) + 0.2 (brand) + 0.4 (model) + 0.1 (explicit condition)
8. If confidence < `llm.confidence_threshold` (default 0.5) and `llm.enabled: true`, falls back to `LLMParser`
9. Listings with final confidence < 0.5 are stored as `status=new` but not valuated

Canonical name examples: `"NVIDIA RTX 3080 10GB"`, `"AMD Ryzen 7 5800X"`, `"Lenovo ThinkPad T460"`, `"Gaming PC RTX 2060"`, `"Sony PS5 Digital Edition"`, `"Apple iPhone 15 Pro Max 256GB"`, `"Apple MacBook Pro 14 M3 Pro 2023"`

## LLM Fallback (title parsing)

- Model: `claude-haiku-4-5` (cheapest, fast, ~$0.001/listing)
- Gated by `llm.enabled: true` in config.yaml
- API key: `llm.api_key` in config.yaml or `ANTHROPIC_API_KEY` env var
- Returns same `ParsedTitle` dataclass as regex parser
- Only called when regex confidence < `llm.confidence_threshold` (default 0.5)

## LLM Validation (misrepresentation filter)

- `pipeline/validate.py` — `run_llm_validate(margin_threshold=300.0)`
- Runs automatically at end of `scan` and `scan all` (CLI + web UI)
- Also available as standalone `hardware-scraper validate` command and **Validate LLM** button in web UI
- Queries all valuations with `margin_pct > margin_threshold` (default 300%)
- Sends title + description to Claude Haiku: "Is this a real [category] or an accessory/service?"
- `DROP` response → valuation deleted, `listing.status = "noise"` (excluded from future valuations)
- `KEEP` response → no change
- Only runs when `llm.enabled: true` and API key is set

## CLI Commands

```powershell
# Always activate venv first
.venv\Scripts\Activate.ps1

# Full pipeline (recommended day-to-day)
hardware-scraper scan                              # browse + scrape all queries + valuate + validate + report
hardware-scraper ui                                # launch web dashboard at http://localhost:8000

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
hardware-scraper validate                          # LLM-check >300% margin listings; drop misrepresentations
hardware-scraper validate --margin 200             # use lower threshold
hardware-scraper report                            # show ranked results (Rich table)
hardware-scraper report --csv                      # also save to data/exports/
hardware-scraper db-upgrade                        # apply Alembic migrations
```

## Web UI

Launch with `hardware-scraper ui` → opens `http://localhost:8000`.

- Dark-themed dashboard showing all valuated listings
- **Scan All** button — runs the full pipeline (browse + all queries + valuate + LLM validate)
- **Browse** / **Scrape** buttons — per-source controls with source selector + keyword input
- **Valuate** button — re-runs margin calculation on new identified listings
- **Validate LLM** button — LLM-checks listings with margin >300% and drops misrepresentations
- Sortable columns: click any column header to sort ascending/descending
- Filters: text search, category, source (OfferUp/Facebook), condition, margin tier
- Stat cards: total listings, profitable count, excellent count, for-parts count, avg margin
- Live job log panel — shows progress while a scan/scrape runs, auto-refreshes
- Results auto-refresh after any job completes

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
  latitude: 41.9762            # North Attleborough MA
  longitude: -71.3326
  radius_miles: 40
  city_marketplace_url: ""     # paste your FB city URL here if lat/lon results are wrong city
                               # e.g. "https://www.facebook.com/marketplace/north-attleborough-ma/"

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
    console: 12.00
    phone: 8.00

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
- **MacBook screen size ordering** — MacBook regex captures size + chip in left-to-right order; if a seller writes "MacBook Pro M3 14-inch" (chip before size), only chip is captured, not size. Acceptable limitation.
- **venv not committed** — the `.venv/` directory is gitignored and must be created fresh on a new machine: `python -m venv .venv && .venv/Scripts/pip install -e ".[dev]" && .venv/Scripts/playwright install chromium`. The `data/` directory must also be created: `mkdir -p data/browser_session data/facebook_session data/ebay_session data/exports`.
- **LLM parser list-vs-dict (fixed 2026-06-16)** — Claude Haiku sometimes returns `[{...}]` instead of `{...}`. `llm_parser.py:_parse_response` now unwraps single-element arrays.
- **$0 price filter (fixed 2026-06-16)** — listings with price ≤ 0 now dropped at ingest.
- **MacBook comp accuracy (fixed 2026-06-16)** — canonical names now include chip gen + year (e.g., `"Apple MacBook Pro 14 M3 2023"`).
- **For-parts eBay search (fixed 2026-06-16)** — `condition=for_parts` now appends "for parts" keyword + uses `LH_ItemCondition=7000` filter.
- **Console/phone categories (added 2026-06-16)** — PS5, Xbox Series X/S, Switch, Steam Deck, iPhone, Galaxy, Pixel now identified and valuated.
- **Parallel scraping safety (fixed 2026-06-16)** — `make_engine()` in `db.py` enables WAL mode + 5s busy timeout; `hardware-scraper scan` runs sources sequentially.
- **Accessory noise filter expanded (2026-06-17)** — 47 regex patterns in `is_accessory_noise()` now catch: console games with model numbers between brand and "game" (e.g. "Xbox Series X game"), Steam Deck/Switch docks, console cases, cleaning services, SSD enclosures. 112 tests all pass.
- **Facebook location via city URL (added 2026-06-17)** — `facebook.city_marketplace_url` config option overrides the lat/lon URL params for browse. Visit facebook.com/marketplace, navigate to your city, and paste the URL into config.yaml. Lat/lon params now also include `radiusUnit=mi`.
- **LLM validation pass (added 2026-06-17)** — `run_llm_validate()` in `pipeline/validate.py` uses Claude Haiku to check listings with margin >300% and deletes valuations that are accessories/services. Runs automatically at end of scan; also available as `hardware-scraper validate` and **Validate LLM** button in web UI.
- **eBay session reuse (added 2026-06-17)** — `EbayScraper.session()` async context manager holds one Playwright browser open for an entire `run_valuate()` call. Previously each product launched and closed a browser (~4-5s overhead each). Now it's a one-time cost. `CompFetcher(scraper=...)` accepts the shared instance.

## For-Parts Strategy

The user is willing to buy and repair broken electronics (CPUs, GPUs, MOBOs, laptops, desktops, gaming consoles). For-parts listings are often the most profitable deals because non-technical sellers dramatically underprice broken items, and common repairs (thermal paste, bent pins, reflow, screen replacement, battery) are cheap.

The eBay comp for `condition=for_parts` now appends "for parts" to the keyword search and uses eBay's condition filter 7000 (For Parts/Not Working), so comps reflect the actual broken-item market.

High-value for-parts targets: PS5 ($100-200 broken → $200-300 parts), RTX 30XX GPUs ($80-150 broken → $150-250 parts), MacBooks with bad battery/screen ($100-200 → $300-600 repaired), iPhones with cracked screens.
