from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup, Tag

_SEARCH_BASE = "https://www.ebay.com/sch/i.html"
_SESSION_DIR = "data/ebay_session"

_CONDITION_FILTER: dict[str, str] = {
    "for_parts": "7000",
    "like_new": "1000|1500|2500",
    "used": "3000",
}


class EbayScraper:
    """
    Fallback eBay sold-listing fetcher using Playwright with stealth mode
    and a persistent session. Used automatically when no API credentials
    are configured.

    Supports two usage modes:
    - Standalone (default): each get_sold_listings() call opens and closes its own
      browser context. Simple but slow when called many times (1 browser launch/product).
    - Shared session: use EbayScraper.session() as an async context manager to hold
      one browser context open across all calls, eliminating per-product launch overhead.
    """

    def __init__(self, context=None) -> None:
        # If a shared context is provided, this instance uses it without closing it.
        self._context = context

    @classmethod
    @asynccontextmanager
    async def session(cls, session_dir: str = _SESSION_DIR):
        """
        Open one persistent browser context and yield a shared EbayScraper that
        reuses it for every get_sold_listings() call. The context is closed on exit.

        Usage:
            async with EbayScraper.session() as scraper:
                for product in products:
                    results = await scraper.get_sold_listings(product.canonical_name)
        """
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=session_dir,
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                yield cls(context=ctx)
            finally:
                await ctx.close()

    async def get_sold_listings(
        self,
        query: str,
        limit: int = 50,
        condition: Optional[str] = None,
    ) -> list[dict]:
        from playwright_stealth import Stealth

        params: dict[str, str] = {
            "_nkw": query.replace(" ", "+"),
            "LH_Sold": "1",
            "LH_Complete": "1",
            "_sacat": "0",
        }
        if condition and condition in _CONDITION_FILTER:
            params["LH_ItemCondition"] = _CONDITION_FILTER[condition]

        base_url = _SEARCH_BASE + "?" + "&".join(f"{k}={v}" for k, v in params.items())

        if self._context is not None:
            # Shared context path: create a fresh page, search, then close the page.
            # The browser process itself stays alive — no launch/teardown overhead.
            page = await self._context.new_page()
            try:
                await Stealth().apply_stealth_async(page)
                return await self._scrape_pages(page, base_url, limit)
            finally:
                await page.close()
        else:
            # Standalone path: open and close the full browser context per call.
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                ctx = await pw.chromium.launch_persistent_context(
                    user_data_dir=_SESSION_DIR,
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await Stealth().apply_stealth_async(page)
                results = await self._scrape_pages(page, base_url, limit)
                await ctx.close()
                return results

    async def _scrape_pages(self, page, base_url: str, limit: int) -> list[dict]:
        results: list[dict] = []
        page_num = 1
        while len(results) < limit:
            url = base_url + f"&_pgn={page_num}"
            for attempt in range(3):
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await page.wait_for_timeout(10_000 * (attempt + 1))
            await page.wait_for_timeout(1500)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            items = soup.select(".srp-results li")
            found = 0
            for item in items:
                parsed = _parse_item(item)
                if parsed:
                    results.append(parsed)
                    found += 1

            if found == 0:
                break
            page_num += 1

        return results[:limit]


def _parse_price(text: str) -> Optional[float]:
    match = re.search(r"\$[\d,]+\.?\d*", text.strip())
    if not match:
        return None
    try:
        return float(match.group().replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _parse_sold_date(item: Tag) -> datetime:
    caption = item.select_one("div.s-card__caption")
    if caption:
        text = caption.get_text(strip=True)
        match = re.search(r"(\w{3} \d+, \d{4})", text)
        if match:
            try:
                return datetime.strptime(match.group(1), "%b %d, %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return datetime.now(timezone.utc)


def _parse_item(item: Tag) -> Optional[dict]:
    classes = item.get("class") or []
    if "s-card" not in classes:
        return None

    listing_id = item.get("data-listingid", "")
    if not listing_id:
        return None

    # Price — skip strikethrough (best-offer-accepted: actual sold price not shown)
    price_tag = item.select_one("span.s-card__price")
    if not price_tag:
        return None
    if "strikethrough" in (price_tag.get("class") or []):
        return None
    sold_price = _parse_price(price_tag.get_text())
    if sold_price is None or sold_price <= 0:
        return None

    # Shipping: rows with a "$" and "deliver" indicate paid shipping
    shipping = 0.0
    for row in item.select(".s-card__attribute-row"):
        text = row.get_text(strip=True)
        if "$" in text and "deliver" in text.lower():
            shipping = _parse_price(text) or 0.0
            break

    return {
        "sold_price": sold_price,
        "shipping": shipping,
        "ebay_item_id": str(listing_id),
        "sold_date": _parse_sold_date(item),
    }
