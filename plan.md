# HardwareScraper — Plan

## Status
Phase 2A complete. Phase 2B next.

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

None currently open. All Phase 2A bugs resolved.

---

## Roadmap

### Phase 2A — Data Quality ✅
- [x] Complete PC detection — desktop/laptop category wins over component; canonical = "Gaming PC RTX 2060"
- [x] Laptop model extraction — ThinkPad T460, MacBook Pro M1, etc. produce distinct eBay queries
- [x] Refurb store filter — blocklist "SHOP", "INV." title patterns
- [x] Per-category shipping estimates in config.yaml (cpu $8, ram $6, ssd $7, desktop $40, etc.)

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
- [ ] Parallel OfferUp keyword scrapes for targeted categories
- [ ] Listing expiry detection — mark sold/removed after N days
- [ ] Goal: thousands of listings per 30-minute cycle

---

## Pipeline
```
OfferUp / Facebook browse or keyword search
    → refurb noise filter (SHOP*, INV.* dropped)
    → title parser (regex)
        desktop/laptop → system-level eBay canonical
        laptop         → brand + specific model
        component      → brand + model + specs
    → LLM fallback if confidence < 0.5
    → store in SQLite (dedup by source + external_id)
    → fetch eBay sold comps (cached 24h)
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

*Last updated: 2026-06-16*
