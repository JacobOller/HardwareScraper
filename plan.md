# HardwareScraper — Plan

## What This Is

A deal-finding system that scrapes local marketplaces 3× daily, has AI confirm each top deal, and pushes results to Discord. Primary focus: broken devices bought cheap, repaired, resold on eBay.

---

## Status

Everything through N3 + scheduling is complete and running.

---

## What's Built

| Feature | Notes |
|---------|-------|
| Scraping — OfferUp, Facebook, Craigslist, eBay Local, Mercari | Browse + keyword search |
| Title parser — category, brand, model, condition | Regex + Claude Haiku fallback |
| Noise filters — accessories, refurb stores, $0 listings | 47+ patterns |
| LLM misrepresentation filter | Drops accessories/services with inflated margins |
| eBay comp fetching — for-parts floor + working-used repair target | Dual comp for broken items |
| Fee formula — eBay 13.25% (`fees.platform: ebay`) | Switch to `amazon` when account matures |
| Margin calculation — 5-tier, per-category shipping | |
| AI confirmation pipeline | Legitimacy + comp sanity + repairability per listing |
| Discord notifications — rich embeds with repair upside + AI reason | Tier 1+2 only |
| Notification dedup — `notifications` table | Won't re-send same listing |
| Scheduled scans — 8am, 1pm, 8pm via Windows Task Scheduler | Logs to `data/notify.log` |
| Web UI — sortable/filterable dashboard | Secondary tool; not primary interface |
| Repair upside delta — `↑$X` badge in UI for for-parts rows | |

---

## What's Next

- [ ] Add error handling for issues with headless browser for any website instead of silent crash. E.g. ebay credentials somehow expire; program may silently crash, but instead should send a message to discord in bold saying that the process was ended due to this specific error.
## Backlog

- [ ] Re-notify on price drop ≥ $10 since last send
- [ ] "Send to Discord" button in web UI
- [ ] `last_seen_at` tracking — mark listings stale after 3 missed scrapes
- [ ] Fuzzy cross-source dedup — same listing on OU + FB → one row
- [ ] Price drop badge — "↓ $X" in UI
- [ ] Multi-ZIP scanning — Providence RI, Worcester MA, Boston MA
- [ ] Image condition scan — Claude Vision on first listing photo

---

## Pipeline

```
Scrape (OfferUp / FB / Craigslist / eBay Local / Mercari)
  → noise filters → parse → store
  → eBay comps: for-parts floor + working-used repair target
  → margin calc (eBay 13.25%)
  → LLM misrep filter
  → AI confirmation (legitimacy + repairability + comp sanity)
  → Discord: top confirmed deals
```

## Margin Formula

```
# Working listings
net_resale = ebay_median − (ebay_median × 0.1325) − outbound_shipping

# For-parts listings (margin calculated against post-repair target)
net_resale = working_comp − (working_comp × 0.1325) − outbound_shipping

profit  = net_resale − asking_price
margin% = profit / asking_price × 100
```

## Margin Tiers

| Tier | Margin | Label |
|------|--------|-------|
| 1 | ≥ 50% | Excellent |
| 2 | 30–49% | Good |
| 3 | 15–29% | Marginal |
| 4 | 0–14% | Low |
| 5 | < 0% | Overpriced |

---
*Last updated: 2026-06-20*
