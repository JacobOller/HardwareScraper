# HardwareScraper — Plan

## Status
Phase 2A complete. Phase 2B (automation/Discord) and Phase 2E (for-parts + consoles) are next priorities.

---

## What Works
- OfferUp scraping — keyword search (`scrape -q`) and empty-query browse (`browse`)
- Facebook Marketplace scraping — keyword search (`fb-scrape -q`) and local browse (`fb-browse`)
- Title parser — regex extracts category, brand, model, specs, condition
  - Desktop/laptop categories take priority over component categories (fixes complete PC misidentification)
  - Laptop brand + model extraction (ThinkPad T460, MacBook Pro M1, EliteBook, XPS, etc.)
- Refurb store filter — `SHOP\d+` / `INV.\d+` patterns dropped before DB write
- LLM fallback — Claude Haiku picks up low-confidence titles the regex misses
- eBay sold comp fetching — Playwright + stealth, median of last 60 days
- Margin calculation — 5-tier system, per-category shipping rates
- SQLite persistence — idempotent, dedup by source + listing ID
- Rich terminal report + CSV export
- Search radius: 40 miles (Lowell MA → past Providence RI)

---

## Known Bugs

### Open
- **MacBook screen size ordering** — The MacBook regex captures size+chip in regex order so "MacBook Pro M3 14" (chip before size) only captures chip, not size. Size must appear before chip in the title for both to be captured. Acceptable for now.

### Fixed
- **LLM parser list-vs-dict** — Claude Haiku sometimes returned `[{...}]` (array) instead of `{...}` (object). Fixed in `llm_parser.py:_parse_response` to unwrap single-element arrays.
- **SQLite write locking on parallel scrapes** — WAL mode (`PRAGMA journal_mode=WAL` + `busy_timeout=5000`) enabled via `make_engine()` in `db.py`; all engine creation now goes through this helper.
- **MacBook/laptop eBay comps too generic** — MacBook regex now captures screen size (14/16-inch), chip variant (M3 Pro/Max/Ultra), and year; canonical names are specific e.g. `"Apple MacBook Pro 14 M3 2023"`.
- **`for_parts` condition not used in eBay search** — `comp_fetcher.py` now appends "for parts" to the keyword and EbayScraper uses `LH_ItemCondition=7000` for the for-parts eBay condition filter.
- **Gaming consoles not recognized** — `console` category added to `_SYSTEM_CATEGORY_PATTERNS`; covers PS5, PS4 Pro, Xbox Series X/S, Switch OLED/Lite, Steam Deck.
- **$0 price listings pass through** — Listings with `price is None or price <= 0` now dropped at ingest before any DB write.
- **Too few for-parts condition triggers** — 16 new patterns added: "no display", "cracked screen", "bent pins", "water damage", "bios only", "no post", etc.

---

## Roadmap

### Phase 2A — Data Quality ✅
- [x] Complete PC detection — desktop/laptop category wins over component; canonical = "Gaming PC RTX 2060"
- [x] Laptop model extraction — ThinkPad T460, MacBook Pro M1, etc. produce distinct eBay queries
- [x] Refurb store filter — blocklist "SHOP", "INV." title patterns
- [x] Per-category shipping estimates in config.yaml (cpu $8, ram $6, ssd $7, desktop $40, etc.)
- [x] LLM parser list-vs-dict bug fixed

### Phase 2B — Automation (next)
- [ ] Wire up APScheduler for 30-minute pipeline loop (scrape → valuate → notify)
- [ ] Discord webhook notifications for Tier 1 and Tier 2 deals
- [ ] `hardware-scraper daemon` CLI command to start the loop

### Phase 2C — Facebook Marketplace ✅
- [x] Playwright scraper with persistent FB session (`data/facebook_session/`)
- [x] Parse FB Relay JSON from embedded script tags; DOM card fallback
- [x] Wired into ingest pipeline as `source: facebook`; `fb-browse` / `fb-scrape` CLI commands

### Phase 2D — Scale
- [ ] Multi-zip scraping (Providence, Worcester, Boston — all within 45 min)
- [ ] SQLite WAL mode to allow parallel keyword scrapes without locking
- [ ] Listing expiry detection — mark sold/removed after N days
- [ ] Goal: thousands of listings per 30-minute cycle

### Phase 2E — For-Parts & Consoles ✅
The biggest untapped opportunity: broken electronics listed by non-technical sellers who
don't know parts value. A broken PS5 at $100 or a GPU with bent pins at $50 can flip for 2-4× profit.

- [x] **For-parts eBay search mode** — `condition == "for_parts"` appends "for parts" to the eBay keyword and uses `LH_ItemCondition=7000` (For parts/not working) filter
- [x] **Expanded for-parts condition detection** — 16 new patterns: "no display", "won't power on", "cracked screen", "bad battery", "bent pins", "water damage", "bad gpu", "no post", "bios only", "sold as is", "no boot", "damaged", "does not turn on", etc.
- [x] **Console category** — `console` in `_SYSTEM_CATEGORY_PATTERNS` (checked before desktop); PS5, Xbox Series X/S, Switch OLED/Lite, Steam Deck, PS4 Pro; brand/model extraction; eBay canonical = "Sony PS5 Digital Edition"
- [x] **iPhone/smartphone category** — `phone` category with iPhone SE/mini/12-15 Pro Max, Galaxy S/A, Pixel patterns; storage spec extraction; $8 shipping
- [x] **For-parts keyword scrape queries** — added to `config.yaml search.queries`: "broken laptop", "broken ps5", "broken xbox", "gpu not working", "for parts desktop", "cracked screen iphone", "iPhone 14", "iPhone 15"
- [x] **Fix laptop canonical names** — MacBook regex now captures screen size (14/16-inch), chip (M1/M2/M3/M5 + Pro/Max/Ultra variant), and year; `"Apple MacBook Pro 14 M3 Pro 2023"` vs old generic `"Apple MacBook Pro"`
- [x] **$0 price filter** — listings with `price is None or price <= 0` dropped before DB write

### Phase 2F — UI & Usability ✅
- [x] **Basic web UI** — FastAPI + plain HTML/JS dashboard at `localhost:8000`; launch with `hardware-scraper ui`. Features: sortable results table (by margin/price/profit/category), filter by category/source/condition/tier, live job log panel, stat cards (total/profitable/excellent/for-parts/avg margin), dark theme.
- [x] **One-click "scan all" command/button** — `hardware-scraper scan` CLI command runs full pipeline: browse OfferUp+FB → scrape all configured queries → valuate → report. Web UI "Scan All" button triggers the same via `/api/scan`.

---

## Pipeline
```
OfferUp / Facebook browse or keyword search
    → refurb noise filter (SHOP*, INV.* dropped)
    → $0-price filter  ← Phase 2E
    → title parser (regex)
        desktop/laptop/console → system-level eBay canonical
        laptop         → brand + specific model + chip gen + year
        component      → brand + model + specs
        for_parts      → mark condition; use parts-market eBay search
    → LLM fallback if confidence < 0.5
    → store in SQLite (dedup by source + external_id)
    → fetch eBay sold comps (cached 24h)
        working units  → standard sold search
        for_parts      → "for parts not working" sold search
    → calculate margin (per-category shipping)
    → Discord notify if Tier 1/2  ← Phase 2B
    → report
```

---

## Margin Formula
```
net_resale = ebay_median − (ebay_median × 0.1325 + $0.30) − outbound_shipping
profit     = net_resale − asking_price
margin%    = profit / asking_price × 100
```

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

*Last updated: 2026-06-16 (Phase 2E + 2F complete)*
