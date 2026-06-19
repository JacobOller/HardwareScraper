# HardwareScraper — Plan

## Status
Phases 2A–2G complete. Phase 2H (Amazon fee structure) partially complete (formula updated; needs config cleanup). Phase 2I is next: bug fixes, display polish, and the issues identified on 2026-06-18.

---

## What Works
- OfferUp scraping — keyword search (`scrape -q`) and empty-query browse (`browse`)
- Facebook Marketplace scraping — keyword search (`fb-scrape -q`) and local browse (`fb-browse`)
- eBay Local scraping — active listings with local pickup filter (`ebay_local` source)
- Craigslist scraping — `craigslist` source, enabled via config
- Mercari scraping — `mercari` source, enabled via config
- Title parser — regex extracts category, brand, model, specs, condition
  - Desktop/laptop categories take priority over component categories (fixes complete PC misidentification)
  - Laptop brand + model extraction (ThinkPad T460, MacBook Pro M1, EliteBook, XPS, etc.)
- Refurb store filter — `SHOP\d+` / `INV.\d+` patterns dropped before DB write
- Accessory noise filter — 47 regex patterns drop phone cases, games, docks, services, enclosures
- LLM fallback — Claude Haiku picks up low-confidence titles the regex misses
- LLM validation — auto-deletes high-margin misrepresentations after scan
- eBay sold comp fetching — Playwright + stealth, median of last 60 days
- eBay session reuse — one browser launch per valuation run instead of per-product
- Margin calculation — 5-tier system, per-category shipping rates, Amazon fee formula
- SQLite persistence — idempotent, dedup by source + listing ID
- Rich terminal report + CSV export
- Web UI — dark dashboard, sortable/filterable table, job log, stat cards
- Search radius: 40 miles (North Attleborough MA → past Providence RI)

---

## Known Bugs

### Open
- **eBay listings display as "OU"** — `dashboard.html:254` maps all non-Facebook sources to "OU". Needs multi-source label handling for `ebay_local`, `craigslist`, `mercari`.
- **MacBook screen size ordering** — The MacBook regex captures size+chip in regex order so "MacBook Pro M3 14" (chip before size) only captures chip, not size. Acceptable for now.
- **eBay Local shows auctions** — `EbayLocalScraper` doesn't filter auction vs BIN listings; many high-volume dealers post auction-format GPU listings that are not actionable.
- **Broken items listed as "used"** — Condition detection only runs on title. Listings where damage is described in the body (e.g., "see description — cracked screen") are stored as `used` not `for_parts`.
- **Non-local eBay listings in results** — eBay local scraper filters by ZIP but some shipped items still appear; margin formula doesn't account for the seller's shipping cost.

### Fixed
- **LLM parser list-vs-dict** — Claude Haiku sometimes returned `[{...}]` (array) instead of `{...}` (object). Fixed in `llm_parser.py:_parse_response` to unwrap single-element arrays.
- **SQLite write locking on parallel scrapes** — WAL mode (`PRAGMA journal_mode=WAL` + `busy_timeout=5000`) enabled via `make_engine()` in `db.py`; all engine creation now goes through this helper.
- **MacBook/laptop eBay comps too generic** — MacBook regex now captures screen size (14/16-inch), chip variant (M3 Pro/Max/Ultra), and year; canonical names are specific e.g. `"Apple MacBook Pro 14 M3 2023"`.
- **`for_parts` condition not used in eBay search** — `comp_fetcher.py` now appends "for parts" to the keyword and EbayScraper uses `LH_ItemCondition=7000` for the for-parts eBay condition filter.
- **Gaming consoles not recognized** — `console` category added to `_SYSTEM_CATEGORY_PATTERNS`; covers PS5, PS4 Pro, Xbox Series X/S, Switch OLED/Lite, Steam Deck.
- **$0 price listings pass through** — Listings with `price is None or price <= 0` now dropped at ingest before any DB write.
- **Too few for-parts condition triggers** — 16 new patterns added: "no display", "won't power on", "cracked screen", "bad battery", "bent pins", "water damage", "bios only", "no post", etc.

---

## Roadmap

### Phase 2A — Data Quality ✅
- [x] Complete PC detection — desktop/laptop category wins over component; canonical = "Gaming PC RTX 2060"
- [x] Laptop model extraction — ThinkPad T460, MacBook Pro M1, etc. produce distinct eBay queries
- [x] Refurb store filter — blocklist "SHOP", "INV." title patterns
- [x] Per-category shipping estimates in config.yaml (cpu $8, ram $6, ssd $7, desktop $40, etc.)
- [x] LLM parser list-vs-dict bug fixed

### Phase 2B — Automation (deferred)
- [ ] Wire up APScheduler for 30-minute pipeline loop (scrape → valuate → notify)
- [ ] Discord webhook notifications for Tier 1 and Tier 2 deals
- [ ] `hardware-scraper daemon` CLI command to start the loop
- [ ] Deal deduplication — only notify for listings not already alerted
- [ ] Multi-ZIP scanning — Providence RI, Worcester MA, Boston MA added to rotation

### Phase 2C — Facebook Marketplace ✅
- [x] Playwright scraper with persistent FB session (`data/facebook_session/`)
- [x] Parse FB Relay JSON from embedded script tags; DOM card fallback
- [x] Wired into ingest pipeline as `source: facebook`; `fb-browse` / `fb-scrape` CLI commands

### Phase 2D — Scale
- [x] SQLite WAL mode to allow parallel keyword scrapes without locking
- [x] **Reuse eBay browser session across valuations** — `EbayScraper.session()` async context manager holds one persistent Playwright context open for the entire `run_valuate()` run.
- [ ] Multi-zip scraping (Providence, Worcester, Boston — all within 45 min)
- [ ] Listing expiry detection — mark sold/removed after N days
- [ ] Goal: thousands of listings per 30-minute cycle

### Phase 2E — For-Parts & Consoles ✅
- [x] For-parts eBay search mode
- [x] Expanded for-parts condition detection (16+ patterns)
- [x] Console category (PS5, Xbox, Switch, Steam Deck)
- [x] iPhone/smartphone category
- [x] For-parts keyword scrape queries in config
- [x] Fix laptop/MacBook canonical names
- [x] $0 price filter

### Phase 2F — UI & Usability ✅
- [x] Basic web UI (FastAPI + HTML/JS)
- [x] One-click Scan All
- [x] Min/max price filters
- [x] Reset DB button
- [x] Saved listings toggle

### Phase 2G — Data Quality (misrepresentations) ✅
- [x] Expanded accessory noise filter (47 patterns)
- [x] LLM validation pass (auto-deletes misrepresentations >300% margin)
- [x] Facebook city URL override

### Phase 2H — Amazon Fee Structure ✅ (partial)
User sells on **Amazon**, not eBay. eBay sold listings are used only as a price reference.

- [x] **Fee formula updated** — `ValuationCalculator` now uses `amazon_referral_rate` (8%) + `amazon_per_item_fee` ($0.99) from config
- [ ] **Clean up config names** — rename legacy `ebay_rate`/`ebay_fixed` fields to `amazon_referral_rate`/`amazon_per_item_fee` everywhere, update CLAUDE.md references
- [ ] **UI/report labels** — change "eBay fees" to "Amazon fees" in dashboard and reports
- [ ] **Per-category Amazon referral rates** — phones 8%, video games 15%, most PC hardware 8%, accessories 15% (currently flat 8%)
- [ ] **Professional vs Individual account flag** — `fees.professional_account: false` config option; Individual = $0.99/item, Professional = $0/item (monthly subscription)

---

### Phase 2I — Bug Fixes & Display Polish ✅ (partial — 2026-06-18)

#### Source label bug in UI ✅
- [x] **Fix "OU" default label** — `dashboard.html` now maps each source explicitly: `offerup` → "OU", `facebook` → "FB", `ebay_local` → "EB", `craigslist` → "CL", `mercari` → "MC"
- [x] **Add `.source-eb`, `.source-cl`, `.source-mc` CSS classes** — amber/teal/pink colors respectively
- [x] **Source filter dropdown** — eBay Local, Craigslist, Mercari added to both the filter `<select>` and the Browse/Scrape source selector

#### eBay Local auction spam ✅
- [x] **Buy It Now filter** — `LH_BIN=1` added to `EbayLocalScraper._build_url()` when `buy_it_now_only=True`; `ebay_local.buy_it_now_only: true` config flag (default true); wired through `_make_scraper()`
- [ ] **Repeat seller detection** — extract seller ID from eBay listing HTML; if same seller appears on 5+ listings in a single scrape, mark as `dealer` and deprioritize in UI
- [ ] **Store seller ID on Listing** — add `seller_id` column to `listings` table (nullable, for sources that expose it)

#### Condition detection from descriptions ✅
- [x] **Check description at ingest** — `TitleParser.parse()` already concatenates `title + description` and runs `detect_condition()` on the combined text; confirmed working
- [x] **Expand condition patterns** — added: "parts only", "no signal", "black screen", "blank screen", "stuck on logo/screen/bios", "screen issues", "physically damaged", "stripped screws", "missing parts", "incomplete", "won't connect", "needs repair", "needs work", "bad battery", "battery dead/swollen/failing", "charge port issue", "liquid damage"; also fixed curly-quote apostrophe encoding bug (was preventing `won't` from matching)
- [ ] **LLM condition check for ambiguous listings** — for listings where title says "see description" or "read below" with price > $50, pass title + description to Claude Haiku to infer condition

#### Non-local eBay listings
- [ ] **`is_local_pickup` flag on RawListing** — add boolean field; EbayLocalScraper sets it based on whether item has a shipping cost shown in HTML
- [ ] **Add `is_local_pickup` column to `listings` table** — nullable bool
- [ ] **Margin adjustment for non-local** — if `is_local_pickup=False`, subtract the seller's listed shipping from comp price (we pay to receive it + Amazon shipping to resell)
- [ ] **"Ship" vs "Local" badge in UI** — show next to source label

---

### Phase 2J — Price Accuracy & Multi-Source Valuation

#### eBay comp quality improvements
- [ ] **Outlier filtering** — before computing median, drop top 10% and bottom 10% of comp prices (reduces impact of outlier sales)
- [ ] **Minimum comp count** — mark valuation as "low confidence" (and dim in UI) if fewer than 3 comps found; don't hide but visually distinguish
- [ ] **Recent-weighted median** — assign weight 2× to comps within 14 days, 1× to comps 15–60 days old; use weighted median instead of simple median
- [ ] **Show comp freshness** — expose `fetched_at` and oldest/newest comp date in UI tooltip or column

#### Amazon price integration
- [ ] **Amazon active listing scraper** — Playwright search `amazon.com/s?k={canonical_name}` with stealth; extract lowest "new" sold-by-Amazon or fulfilled-by-Amazon price
- [ ] **Use Amazon price as primary resale reference** — since that's the actual sell platform; compare vs eBay median and use the more conservative (lower) estimate
- [ ] **Cache Amazon price per product** — same 24h TTL as eBay comps; store in new `amazon_comps` table or add columns to `products`
- [ ] **Show both prices in UI** — "eBay: $X | AMZ: $Y" so user can see spread
- [ ] **Per-category fee rates** — phones/accessories 8%, video games 15%, most PC hardware 8%; look up by product category in calculator

---

### Phase 2K — UI & Filtering Improvements

- [ ] **Default min_margin_to_show to 15%** — change `config.yaml` `output.min_margin_to_show` from -9999 to 15; Tier 4/5 hidden by default
- [ ] **"Show unprofitable" toggle in web UI** — checkbox to show Tier 4 (Low) and Tier 5 (Overpriced); off by default
- [ ] **Show listing age** — add "Days old" column computed from `scraped_at`; sort by it to find freshest deals
- [ ] **Show eBay comp count** — already in API response (`comp_count`); add column or tooltip in UI
- [ ] **"Notes" field on saved listings** — allow user to add a short personal memo to a saved listing (e.g. "emailed seller", "offered $80"); persist in DB
- [ ] **Bulk actions** — select multiple listings → bulk save, bulk delete, bulk mark noise
- [ ] **Export saved listings only** — CSV export that only includes saved/starred listings

---

### Phase 2L — Data Quality: Freshness, Dedup, Seller Intel

#### Cross-platform deduplication
- [ ] **Fuzzy cross-source dedup** — when a new listing comes in, check if an existing listing from another source has same price (±$5) and similar title (>85% token overlap); link them as duplicates so only one appears in UI
- [ ] **Merged "best URL" display** — when dupes found, show OU + FB icons on one row instead of two rows

#### Listing freshness & expiry
- [ ] **"Last seen" tracking** — on each scrape, update a `last_seen_at` column for existing listings; listings not seen in 3+ scrapes marked `status=stale`
- [ ] **Stale filter in UI** — hide stale listings by default; toggle to show
- [ ] **Listing age alert** — visual indicator when listing is 5+ days old (likely sold)

#### Price drop detection
- [ ] **Price history column** — store `price_history` as JSON on `Listing` (list of `{price, date}` records); update on each re-scrape
- [ ] **Price drop badge** — in UI, show "↓ $X" if price dropped since first seen; sort by biggest recent drops
- [ ] **Price drop notification** — if price drops on a saved listing, flag it prominently (or Discord notify)

#### Seller reputation
- [ ] **Seller ID extraction** — OfferUp exposes seller profile in `__NEXT_DATA__`; Facebook in Relay store; eBay local via listing HTML
- [ ] **Repeat seller flagging** — seller with 5+ active listings = "dealer" (they know prices, won't negotiate); show dealer badge in UI
- [ ] **Known good sellers** — allow user to star sellers; their listings get a "trusted" badge

---

### Phase 2M — Advanced Features (Backlog)

- [ ] **Negotiation calculator** — for each listing, show "smart offer" = asking × 0.70 (or whatever leaves target margin); display as suggested opening bid
- [ ] **Image condition scan** — pass first listing photo URL to Claude Vision API; detect visible damage (cracks, burn marks, missing components); auto-update condition if LLM detects damage
- [ ] **Batch/bundle detector** — flag sellers who have 3+ related component listings (e.g., seller with CPU + GPU + mobo); suggest reaching out about a bundle discount
- [ ] **Amazon ASIN + sales rank lookup** — after finding Amazon price, also pull sales rank; items with rank < 10,000 in Electronics sell within days; items > 500,000 may sit for months
- [ ] **Demand scoring** — combine eBay comp count + Amazon sales rank into a "demand score" shown in UI; high demand = faster flip
- [ ] **Craigslist scraper tuning** — already in codebase (`scrapers/craigslist.py`); free postings often have motivated sellers; tune rate limits and add to scan
- [ ] **Mercari scraper tuning** — already in codebase (`scrapers/mercari.py`); lower avg prices; add to scan rotation

---

## Pipeline
```
OfferUp / Facebook / eBay Local / Craigslist / Mercari browse or keyword search
    → refurb noise filter (SHOP*, INV.* dropped)
    → accessory noise filter (47+ patterns)
    → $0-price filter
    → title parser (regex)
        desktop/laptop/console → system-level eBay canonical
        laptop         → brand + specific model + chip gen + year
        component      → brand + model + specs
        for_parts      → mark condition; use parts-market eBay search
    → description-based condition check (Phase 2I)
    → LLM fallback if confidence < 0.5
    → store in SQLite (dedup by source + external_id)
    → fetch eBay sold comps (cached 24h)
        working units  → standard sold search, outlier-filtered (Phase 2J)
        for_parts      → "for parts not working" sold search
    → fetch Amazon active price (Phase 2J)
    → calculate margin (per-category shipping, Amazon fees)
    → LLM validation pass (>300% margin listings checked for misrepresentations)
    → Discord notify if Tier 1/2  (Phase 2B)
    → report
```

---

## Margin Formula
```
net_resale  = ebay_median − (ebay_median × 0.08 + 0.99) − outbound_shipping
profit      = net_resale − asking_price
margin%     = profit / asking_price × 100
```

Fees: 8% Amazon electronics referral rate + $0.99 individual seller per-item fee.
Outbound shipping is per-category (see `config.yaml` `shipping.by_category`).

## Margin Tiers
| Tier | Margin | Label | Action |
|------|--------|-------|--------|
| 1 | ≥ 50% | Excellent | Act immediately |
| 2 | 30–49% | Good | Worth pursuing |
| 3 | 15–29% | Marginal | Only if convenient |
| 4 | 0–14% | Low | Skip |
| 5 | < 0% | Overpriced | Ignore |

---

*Last updated: 2026-06-18 (Phase 2I–2M checklist added; bug register updated)*
