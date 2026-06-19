from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from bs4 import BeautifulSoup, Tag

from .base import BaseScraper, RawListing

_SEARCH_BASE = "https://www.ebay.com/sch/i.html"
# Electronics category (sacat=293) used for browse with no keyword
_ELECTRONICS_CAT = "293"
_ITEM_ID_RE = re.compile(r"/itm/(\d+)")
_PRICE_RE = re.compile(r"\$([\d,]+\.?\d*)")
_SESSION_DIR = "data/ebay_session"


class EbayLocalScraper(BaseScraper):
    """
    Scrapes active eBay listings with 'local pickup only' filter, within ZIP radius.

    These listings are often underpriced because sellers want a quick local sale and
    avoid shipping hassle. We buy locally and resell nationally on Amazon.

    Uses the same Playwright + stealth + persistent session as EbayScraper (shared dir).
    search() finds keyword results; browse() browses the Electronics category locally.

    Use session() to hold the browser open across multiple search()/browse() calls.
    """

    def __init__(
        self,
        zip_code: str = "",
        radius_miles: int = 40,
        rate_limit_seconds: float = 3.0,
        headless: bool = True,
        buy_it_now_only: bool = True,
    ) -> None:
        super().__init__(rate_limit_seconds)
        self._zip = zip_code
        self._radius = radius_miles
        self._headless = headless
        self._bin_only = buy_it_now_only

    def _build_url(self, query: str = "", sacat: str = "0", page: int = 1) -> str:
        params = {
            "_nkw": query.replace(" ", "+") if query else "",
            "LH_PrefLoc": "99",   # local pickup only
            "_stpos": self._zip,
            "_sadis": str(self._radius),
            "_sacat": sacat,
            "_pgn": str(page),
            "rt": "nc",
        }
        if self._bin_only:
            params["LH_BIN"] = "1"   # Buy It Now only — excludes auction-format dealer spam
        return _SEARCH_BASE + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    @asynccontextmanager
    async def session(self):
        """Hold one browser open for the duration. Reused across search()/browse() calls."""
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
        async with async_playwright() as pw:
            self._browser = await pw.chromium.launch_persistent_context(
                user_data_dir=_SESSION_DIR,
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()
            await Stealth().apply_stealth_async(page)
            try:
                yield self
            finally:
                await self._browser.close()
                self._browser = None

    async def search(self, query: str, limit: int = 50) -> AsyncIterator[RawListing]:
        async for listing in self._scrape(query=query, limit=limit):
            yield listing

    async def browse(self, limit: int = 100) -> AsyncIterator[RawListing]:
        async for listing in self._scrape(query="", sacat=_ELECTRONICS_CAT, limit=limit):
            yield listing

    async def _scrape(
        self, query: str = "", sacat: str = "0", limit: int = 50
    ) -> AsyncIterator[RawListing]:
        """Route to session-reuse path or standalone launch based on self._browser."""
        if self._browser:
            page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()
            async for listing in self._scrape_page(page, query, sacat, limit):
                yield listing
        else:
            from playwright.async_api import async_playwright
            from playwright_stealth import Stealth
            async with async_playwright() as pw:
                ctx = await pw.chromium.launch_persistent_context(
                    user_data_dir=_SESSION_DIR,
                    headless=self._headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await Stealth().apply_stealth_async(page)
                try:
                    async for listing in self._scrape_page(page, query, sacat, limit):
                        yield listing
                finally:
                    await ctx.close()

    async def _scrape_page(
        self, page, query: str, sacat: str, limit: int
    ) -> AsyncIterator[RawListing]:
        seen: set[str] = set()
        count = 0
        page_num = 1

        while count < limit:
            url = self._build_url(query=query, sacat=sacat, page=page_num)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2000)

            html = await page.content()
            listings = _parse_active_listings(html)
            if not listings:
                break

            found_new = False
            for listing in listings:
                if listing.external_id in seen or count >= limit:
                    continue
                seen.add(listing.external_id)
                yield listing
                count += 1
                found_new = True

            if not found_new:
                break
            page_num += 1
            await self._sleep()


def _parse_active_listings(html: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[RawListing] = []

    items = soup.select(".srp-results li")
    for item in items:
        classes = item.get("class") or []
        parsed: Optional[RawListing] = None

        if "s-card" in classes:
            parsed = _parse_s_card(item)
        elif "s-item" in classes:
            parsed = _parse_s_item(item)

        if parsed:
            results.append(parsed)

    return results


def _parse_s_card(item: Tag) -> Optional[RawListing]:
    """Parse items in eBay's 2024+ s-card redesign (same structure as sold listings)."""
    listing_id = str(item.get("data-listingid", "")).strip()
    if not listing_id:
        return None

    price_tag = item.select_one("span.s-card__price")
    if not price_tag:
        return None
    price = _parse_price(_first_price_text(price_tag))
    if price is None or price <= 0:
        return None

    title = _extract_title_s_card(item)
    if not title:
        return None

    is_local_pickup = _detect_local_pickup_s_card(item)

    return RawListing(
        source="ebay_local",
        external_id=listing_id,
        url=f"https://www.ebay.com/itm/{listing_id}",
        title=title,
        price=price,
        is_local_pickup=is_local_pickup,
    )


def _parse_s_item(item: Tag) -> Optional[RawListing]:
    """Parse items in eBay's classic s-item layout."""
    link = item.select_one("a.s-item__link")
    if not link:
        return None
    href = link.get("href", "")
    m = _ITEM_ID_RE.search(href)
    if not m:
        return None
    listing_id = m.group(1)

    price_tag = item.select_one("span.s-item__price")
    if not price_tag:
        return None
    price = _parse_price(_first_price_text(price_tag))
    if price is None or price <= 0:
        return None

    title_el = (
        item.select_one("div.s-item__title span.BOLD")
        or item.select_one("span.BOLD")
        or item.select_one("div.s-item__title")
    )
    title = title_el.get_text(strip=True) if title_el else ""
    if not title or title.lower() == "shop on ebay":
        return None

    is_local_pickup = _detect_local_pickup_s_item(item)

    return RawListing(
        source="ebay_local",
        external_id=listing_id,
        url=f"https://www.ebay.com/itm/{listing_id}",
        title=title,
        price=price,
        is_local_pickup=is_local_pickup,
    )


def _detect_local_pickup_s_card(item: Tag) -> bool:
    """Check s-card attribute rows for local pickup vs. paid shipping indicator."""
    for row in item.select(".s-card__attribute-row"):
        text = row.get_text(strip=True).lower()
        if "local pickup" in text:
            return True
        if "shipping" in text and "$" in row.get_text():
            return False
    return True  # default: assume local (filter was LH_PrefLoc=99)


def _detect_local_pickup_s_item(item: Tag) -> bool:
    """Check s-item shipping detail for local pickup vs. paid shipping indicator."""
    for sel in (".s-item__shipping", ".s-item__detail--primary", ".s-item__logisticsCost"):
        el = item.select_one(sel)
        if el:
            text = el.get_text(strip=True).lower()
            if "local pickup" in text:
                return True
            if "shipping" in text and "$" in el.get_text():
                return False
    return True  # default: assume local


def _extract_title_s_card(item: Tag) -> str:
    """Try several selectors to pull a title from an s-card item."""
    for sel in (
        "span.s-card__title",
        "a.s-card__title",
        "h3.s-card__title",
        "[role='heading']",
        "h3",
        "span.BOLD",
    ):
        el = item.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text and text.lower() not in ("shop on ebay",):
                return text
    return ""


def _first_price_text(price_tag: Tag) -> str:
    """Return the first price-like string (handles 'to' ranges by taking lower bound)."""
    text = price_tag.get_text(separator=" ", strip=True)
    # "US $100.00 to US $150.00" → take the first price
    return text.split(" to ")[0]


def _parse_price(text: str) -> Optional[float]:
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None
