# HardwareScraper — Claude Reference

## What This Project Does

Finds underpriced broken electronics on local marketplaces (OfferUp, Facebook, Craigslist, eBay Local, Mercari), uses eBay sold comps to estimate resale value, has Claude AI confirm each deal, and sends the top results to Discord 3× daily. Primary focus: buy broken devices cheap, repair, resell on eBay.

## Current State

All phases complete. Discord notifications run automatically at 8am, 1pm, 8pm via Windows Task Scheduler. Web UI exists as a secondary tool for browsing history.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.14 (venv at `.venv/`) |
| Browser automation | Playwright (headless, persistent session) + playwright-stealth |
| Database | SQLite (`data/hardware_scraper.db`) |
| ORM / migrations | SQLAlchemy 2.0 + Alembic |
| Scheduling | Windows Task Scheduler → `scripts/run_notify.ps1` |
| CLI | Typer (`hardware-scraper` command) |
| Config | YAML + pydantic-settings (`config.yaml`) |
| LLM | Anthropic SDK — `claude-haiku-4-5` |
| HTML parsing | BeautifulSoup4 |

## Project Structure

```
HardwareScraper/
├── config.yaml
├── src/hardware_scraper/
│   ├── cli.py                    # all CLI commands
│   ├── config.py                 # YAML → pydantic, singleton get_config()
│   ├── models/
│   │   ├── listing.py            # Listing
│   │   ├── product.py            # Product + ListingProduct
│   │   ├── valuation.py          # EbayComp + Valuation (incl. working_comp_price)
│   │   └── notification.py       # Notification (dedup sent listings)
│   ├── scrapers/
│   │   ├── offerup.py
│   │   ├── facebook.py
│   │   ├── craigslist.py
│   │   ├── ebay_local.py
│   │   └── mercari.py
│   ├── parsers/
│   │   ├── category_rules.py     # regex patterns, noise filters
│   │   ├── title_parser.py       # TitleParser → ParsedTitle + confidence
│   │   └── llm_parser.py         # Claude Haiku fallback for low-confidence titles
│   ├── ebay/
│   │   ├── comp_fetcher.py       # fetches + caches eBay comps; dual comp for for_parts
│   │   └── scraper.py            # Playwright eBay scraper with shared session
│   ├── valuation/
│   │   └── calculator.py         # margin formula, fee platform branching
│   ├── pipeline/
│   │   ├── ingest.py             # scrape → filter → parse → store
│   │   ├── valuate.py            # fetch comps → calculate margins
│   │   ├── validate.py           # LLM misrepresentation filter
│   │   └── notify.py             # AI confirmation + Discord send
│   └── web/
│       ├── app.py                # FastAPI routes
│       └── dashboard.html        # dark UI dashboard
├── scripts/
│   ├── run_notify.ps1            # Task Scheduler wrapper (logs to data/notify.log)
│   ├── reset_valuations.py       # clear comps+valuations for re-run
│   ├── check_db.py               # full DB dump
│   └── debug_ebay.py             # eBay scraper diagnostic
└── alembic/versions/             # DB migrations
```

## Key Data Models

**`listings`** — source, external_id, url, title, price, description, condition, is_local_pickup, status, saved, hidden

**`products`** — category, brand, model, canonical_name (used as eBay search key)

**`ebay_comps`** — product_id, condition (`"for_parts"` or `"working_used"` or `"used"`), sold_price, sold_date

**`valuations`** — ebay_median_price (for-parts floor), working_comp_price (repair target), estimated_fees, net_resale, profit, margin_pct, margin_tier

**`notifications`** — listing_id, sent_at, margin_pct_at_send, ai_verdict (JSON)

## Margin Formula

`fees.platform` in config controls which rate applies.

```
# For working listings:
resale_ref = ebay_median_price

# For for_parts listings:
resale_ref = working_comp_price  (what it sells for repaired — the actual target)
floor      = ebay_median_price   (what broken ones sell for — shown as ↑$X upside in UI)

# fees.platform: ebay (current)
net_resale = resale_ref − (resale_ref × 0.1325) − outbound_shipping
profit     = net_resale − asking_price − inbound_shipping
margin%    = profit / asking_price × 100

# fees.platform: amazon (when account matures)
net_resale = resale_ref − (resale_ref × 0.08 + 0.99) − outbound_shipping
```

## Margin Tiers

| Tier | Margin | Label |
|------|--------|-------|
| 1 | ≥ 50% | Excellent |
| 2 | 30–49% | Good |
| 3 | 15–29% | Marginal |
| 4 | 0–14% | Low |
| 5 | < 0% | Overpriced |

Discord notifies on Tier 1 + 2 only (configurable via `notifications.min_margin_tier`).

## Discord Notification Pipeline

`pipeline/notify.py` — `run_notify()`:
1. Query all Tier 1/2 `valuated` listings not in `notifications` table
2. Rank: for-parts with repair upside ≥ $50 first, then by margin%; cap at 10
3. For each candidate, send structured prompt to Claude Haiku:
   - Legitimacy check (real hardware, not accessory/scam)
   - Comp sanity check (is margin realistic?)
   - Repairability (for-parts only): difficulty + cost estimate
   - Returns JSON: `{ verdict, reason, repair_difficulty, repair_cost }`
4. On `NOTIFY`: POST Discord embed + write `notifications` row
5. On `SKIP`: log reason, move on (listing stays candidate for next run)

Embed includes: asking price, margin, both eBay comps (for-parts), repair upside, AI one-liner.

## CLI Commands

```powershell
.venv\Scripts\Activate.ps1

# Primary
.venv\Scripts\python.exe -m hardware_scraper.cli scan-and-notify   # full pipeline + Discord
.venv\Scripts\python.exe -m hardware_scraper.cli notify            # notify only (test)
hardware-scraper ui                                                 # web UI at localhost:8000

# Scraping
hardware-scraper browse                            # OfferUp local browse
hardware-scraper scrape --query "RTX 3080"         # OfferUp keyword
hardware-scraper fb-browse                         # Facebook local browse
hardware-scraper fb-scrape --query "RTX 3080"      # Facebook keyword
hardware-scraper cl-browse                         # Craigslist browse
hardware-scraper cl-scrape --query "RTX 3080"      # Craigslist keyword
hardware-scraper ebay-local-scrape --query "GPU"   # eBay local pickup
hardware-scraper mercari-scrape --query "RTX 3080" # Mercari keyword

# Valuation & pipeline
hardware-scraper valuate                           # fetch comps + calculate margins
hardware-scraper validate                          # LLM misrep filter (>60% margin)
hardware-scraper report                            # Rich table output
hardware-scraper report --csv                      # export to data/exports/
hardware-scraper db-upgrade                        # apply Alembic migrations

# Scheduling (Task Scheduler calls this)
powershell -File scripts\run_notify.ps1            # logs to data\notify.log
```

Note: `hardware-scraper` launcher has a Windows bug — use `python -m hardware_scraper.cli` for scheduled/scripted calls.

## Scheduled Tasks

Three Windows Task Scheduler tasks created via `schtasks`:
- `HardwareScraper-0800` — 8:00 AM daily
- `HardwareScraper-1300` — 1:00 PM daily
- `HardwareScraper-2000` — 8:00 PM daily

Each runs `scripts/run_notify.ps1` which logs timestamped output to `data/notify.log` (rotates at 5MB).

To trigger manually: `schtasks /Run /TN "HardwareScraper-0800"`
To check log live: `Get-Content data\notify.log -Wait -Tail 20`

## config.yaml Key Values

```yaml
notifications:
  discord_webhook_url: ""         # Discord channel webhook URL
  min_margin_tier: 2              # notify Tier 1 + 2
  max_per_run: 10
  for_parts_min_repair_upside: 50

fees:
  platform: ebay                  # ebay = 13.25%; amazon = 8% + $0.99
  ebay_rate: 0.1325

llm:
  enabled: true
  api_key: ${ANTHROPIC_API_KEY}
  model: "claude-haiku-4-5"
  confidence_threshold: 0.5
  validate_margin_threshold: 60

scraping:
  location_zip: "02766"
  radius_miles: 40
  headless: true

facebook:
  headless: true                  # false for first login only
  city_marketplace_url: ""        # paste FB marketplace city URL if lat/lon gives wrong city

shipping:
  default: 15.00
  by_category:
    cpu: 8.00    gpu: 15.00   laptop: 15.00  console: 12.00
    ram: 6.00    ssd: 7.00    desktop: 40.00 phone: 8.00
```

## For-Parts Strategy

Primary profit source. Non-technical sellers underprice broken hardware drastically.

For `for_parts` listings, two eBay comps are fetched:
- **Floor** (`condition="for_parts"`, `LH_ItemCondition=7000`): what broken ones sell for — shown as the baseline
- **Repair target** (`condition="working_used"`, used filter): what working ones sell for — used in margin calculation

Repair upside (`working_comp − floor`) is shown as `↑$X` in the UI and in Discord embeds. The AI confirmation pass specifically assesses repair difficulty and cost for broken items.

High-value targets: PS5 HDMI port ($10-15 repair), RTX 30XX GPUs, MacBooks with bad battery/screen, iPhones with cracked screens.

## Known Gotchas

- **Windows launcher bug** — `hardware-scraper` entry point fails with "Fatal error in launcher". Use `python -m hardware_scraper.cli` instead for any scripted/scheduled invocation.
- **Discord webhook domain** — `discordapp.com` URLs return 403. Code normalizes to `discord.com` automatically.
- **eBay selectors change** — if comps stop returning results, run `scripts/debug_ebay.py` to check HTML structure.
- **OfferUp `__NEXT_DATA__` path** — changed once; legacy path kept as fallback in `_extract_listings`.
- **Facebook first login** — set `facebook.headless: false`, run `fb-browse`, log in manually, then set back to `true`.
- **Comp cache** — all comps cached 24h per (product_id, condition). Run `scripts/reset_valuations.py` to force fresh fetch.
- **Amazon scraper** — disabled by default (`amazon.enabled: false`). Bot detection is aggressive; enable only if willing to handle CAPTCHAs.
- **MacBook chip-before-size** — "MacBook Pro M3 14-inch" only captures chip, not screen size. Acceptable limitation.
