"""Notification pipeline — AI confirmation + Discord send.

Queries top Tier 1/2 listings not yet notified, runs each through Claude Haiku
for a legitimacy + profitability + repairability check, then POSTs confirmed
deals to Discord as rich embeds.
"""
from __future__ import annotations

import datetime
import json
import os
import urllib.request
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from hardware_scraper.config import get_config
from hardware_scraper.db import make_engine
from hardware_scraper.models import Listing, ListingProduct, Product, Valuation
from hardware_scraper.models.notification import Notification


_AI_PROMPT = """\
You are evaluating a local marketplace deal for someone who buys, repairs, and resells electronics on eBay.

Listing:
  Title: {title}
  Category: {category}
  Condition: {condition}
  Asking price: ${price:.0f}
  Description: {description}

eBay comps:
  {comp_lines}

Calculated margin: {margin_pct:.1f}% ({margin_label})

Evaluate this listing. Be strict — only NOTIFY for deals that are clearly worth acting on.

Check:
1. Is this real hardware actually for sale (not an accessory, game, service, or scam)?
2. Is the margin realistic — do the comps actually support the asking price calculation?
3. For broken/for-parts: is the described fault a known cheap repair, or high-risk damage?

Respond with JSON only, no other text:
{{
  "legitimate": true,
  "verdict": "NOTIFY",
  "reason": "one sentence summary of why this is or isn't worth buying",
  "repair_difficulty": "easy" or "medium" or "hard" or null,
  "repair_cost": "$X-Y estimate" or null
}}"""


_TIER_COLORS = {1: 0x22C55E, 2: 0x3B82F6}  # green, blue


async def run_notify(log_fn: Optional[Callable[[str], None]] = None) -> int:
    """Run AI confirmation on top candidates and send Discord notifications.

    Returns the number of listings sent.
    """
    def _log(msg: str) -> None:
        print(msg)
        if log_fn:
            log_fn(msg)

    cfg = get_config()
    notif_cfg = cfg.notifications

    if not notif_cfg.discord_webhook_url:
        _log("Notify skipped: notifications.discord_webhook_url not set in config")
        return 0

    if not cfg.llm.enabled:
        _log("Notify skipped: llm.enabled is false — AI confirmation required")
        return 0

    api_key = cfg.llm.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        _log("Notify skipped: no API key (set llm.api_key or ANTHROPIC_API_KEY)")
        return 0

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
    except ImportError:
        _log("Notify skipped: anthropic package not installed")
        return 0

    engine = make_engine(cfg.database.url)
    sent = 0

    with Session(engine) as db:
        # IDs already notified — skip them
        notified_ids: set[int] = {
            row[0] for row in db.execute(select(Notification.listing_id)).all()
        }

        # Fetch Tier 1+2 valuated listings not yet notified
        rows = db.execute(
            select(Listing, Valuation, ListingProduct, Product)
            .join(Valuation, Valuation.listing_id == Listing.id)
            .join(ListingProduct, ListingProduct.listing_id == Listing.id)
            .join(Product, Product.id == ListingProduct.product_id)
            .where(
                Listing.status == "valuated",
                Listing.hidden == False,
                Valuation.margin_tier <= notif_cfg.min_margin_tier,
            )
            .order_by(Valuation.margin_pct.desc())
        ).all()

        # Filter out already-notified listings
        candidates = [
            (listing, val, lp, product)
            for listing, val, lp, product in rows
            if listing.id not in notified_ids
        ]

        if not candidates:
            _log("Notify: no new Tier 1/2 candidates")
            return 0

        # Rank: for-parts with high repair upside first, then by margin
        def _rank_key(row):
            listing, val, lp, product = row
            repair_upside = (
                (val.working_comp_price - val.ebay_median_price)
                if val.working_comp_price and val.ebay_median_price
                else 0
            )
            is_for_parts = lp.condition == "for_parts"
            # Sort descending: for_parts with upside ≥ threshold first, then all by margin
            return (
                1 if (is_for_parts and repair_upside >= notif_cfg.for_parts_min_repair_upside) else 0,
                val.margin_pct,
            )

        candidates.sort(key=_rank_key, reverse=True)
        candidates = candidates[: notif_cfg.max_per_run]

        _log(f"Notify: AI-confirming {len(candidates)} candidates...")

        # Collect confirmed deals before sending so we can post a batch header first
        confirmed: list[tuple] = []
        for listing, val, lp, product in candidates:
            repair_upside = (
                val.working_comp_price - val.ebay_median_price
                if val.working_comp_price and val.ebay_median_price
                else None
            )

            # Build comp lines for prompt
            comp_lines: list[str] = []
            if lp.condition == "for_parts" and val.working_comp_price:
                comp_lines.append(
                    f"Working/used median: ${val.working_comp_price:.0f} ({val.working_comp_count or '?'} comps) — post-repair resale target"
                )
                comp_lines.append(
                    f"For-parts/broken median: ${val.ebay_median_price:.0f} ({val.ebay_comp_count} comps) — floor if unsold broken"
                )
            else:
                comp_lines.append(
                    f"Used median: ${val.ebay_median_price:.0f} ({val.ebay_comp_count} comps)"
                )

            prompt = _AI_PROMPT.format(
                title=listing.title,
                category=product.category,
                condition=lp.condition.replace("_", " "),
                price=listing.price,
                description=(listing.description or "no description").strip()[:400],
                comp_lines="\n  ".join(comp_lines),
                margin_pct=val.margin_pct,
                margin_label=val.margin_label,
            )

            verdict_data: dict = {}
            try:
                response = await client.messages.create(
                    model=cfg.llm.model,
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = response.content[0].text.strip()
                # Strip markdown code fences if present
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                verdict_data = json.loads(raw)
            except Exception as exc:
                _log(f"  AI error for listing {listing.id}: {exc} — skipping")
                continue

            verdict = verdict_data.get("verdict", "SKIP").upper()
            reason = verdict_data.get("reason", "")
            repair_difficulty = verdict_data.get("repair_difficulty")
            repair_cost = verdict_data.get("repair_cost")

            _log(f"  {verdict} ({val.margin_pct:.0f}%) {listing.title[:55]} — {reason}")

            if verdict != "NOTIFY":
                continue

            confirmed.append((listing, val, lp, product, repair_upside, reason, repair_difficulty, repair_cost, verdict_data))

        if not confirmed:
            _log("Notify: no deals passed AI confirmation")
            return 0

        # Send batch header so runs are visually separated in Discord
        now = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
        header = f"**HardwareScraper — {now} Run** · {len(confirmed)} deal{'s' if len(confirmed) != 1 else ''} found"
        try:
            _post_discord(notif_cfg.discord_webhook_url, content=header)
        except Exception as exc:
            _log(f"  Discord header send failed: {exc}")

        for listing, val, lp, product, repair_upside, reason, repair_difficulty, repair_cost, verdict_data in confirmed:
            embed = _build_embed(
                listing=listing,
                val=val,
                lp=lp,
                product=product,
                repair_upside=repair_upside,
                reason=reason,
                repair_difficulty=repair_difficulty,
                repair_cost=repair_cost,
            )

            try:
                _post_discord(notif_cfg.discord_webhook_url, embed=embed)
            except Exception as exc:
                _log(f"  Discord send failed for listing {listing.id}: {exc}")
                continue

            db.add(Notification(
                listing_id=listing.id,
                margin_pct_at_send=val.margin_pct,
                ai_verdict=json.dumps(verdict_data),
            ))
            db.commit()
            sent += 1

    _log(f"Notify done: {sent} sent")
    return sent


def _build_embed(
    listing, val, lp, product, repair_upside, reason, repair_difficulty, repair_cost
) -> dict:
    condition_label = lp.condition.replace("_", " ").upper()
    source_label = {
        "offerup": "OfferUp", "facebook": "Facebook", "ebay_local": "eBay Local",
        "craigslist": "Craigslist", "mercari": "Mercari",
    }.get(listing.source, listing.source)

    color = _TIER_COLORS.get(val.margin_tier, 0x6B7280)

    fields = [
        {"name": "Ask", "value": f"${listing.price:.0f}", "inline": True},
        {"name": "Margin", "value": f"{val.margin_pct:.1f}% — {val.margin_label}", "inline": True},
        {"name": "Source", "value": f"{source_label} · {condition_label}", "inline": True},
    ]

    if lp.condition == "for_parts" and val.working_comp_price:
        fields.append({
            "name": "eBay (working/repaired)",
            "value": f"${val.working_comp_price:.0f} ({val.working_comp_count or '?'} comps)",
            "inline": True,
        })
        fields.append({
            "name": "eBay (broken floor)",
            "value": f"${val.ebay_median_price:.0f} ({val.ebay_comp_count} comps)",
            "inline": True,
        })
        if repair_upside and repair_upside > 0:
            fields.append({
                "name": "Repair Upside",
                "value": f"+${repair_upside:.0f}",
                "inline": True,
            })
        if repair_difficulty or repair_cost:
            repair_str = repair_difficulty or ""
            if repair_cost:
                repair_str += f" · {repair_cost}"
            fields.append({"name": "Repair", "value": repair_str.strip(" ·"), "inline": True})
    else:
        fields.append({
            "name": "eBay Sold Median",
            "value": f"${val.ebay_median_price:.0f} ({val.ebay_comp_count} comps)",
            "inline": True,
        })

    fields.append({"name": "AI", "value": reason, "inline": False})

    return {
        "title": listing.title[:256],
        "url": listing.url,
        "color": color,
        "fields": fields,
        "footer": {"text": f"HardwareScraper · {product.category}"},
    }


def _post_discord(webhook_url: str, embed: dict | None = None, content: str | None = None) -> None:
    # Normalize legacy discordapp.com domain to discord.com
    url = webhook_url.replace("discordapp.com", "discord.com")
    body: dict = {}
    if embed:
        body["embeds"] = [embed]
    if content:
        body["content"] = content
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "HardwareScraper/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"Discord returned HTTP {resp.status}")
