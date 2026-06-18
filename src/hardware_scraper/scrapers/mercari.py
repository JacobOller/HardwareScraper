from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from .base import BaseScraper, RawListing

_SEARCH_URL = "https://www.mercari.com/search/?keyword={query}&status=on_sale"
_ITEM_ID_RE = re.compile(r"/item/([a-zA-Z]\d+)")
_PRICE_RE = re.compile(r"\$([\d,]+)")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class MercariScraper(BaseScraper):
    """
    Playwright-based Mercari scraper. No persistent session or login needed.

    Mercari is nationwide (not local), so listings require inbound shipping to you.
    Factor that into your margin expectations — a $10-20 inbound shipping cost applies
    to every buy, reducing profit vs. local marketplace sources.

    Tries to extract items from __NEXT_DATA__ JSON first; falls back to DOM scraping.
    Scrolls incrementally to load more items.

    Use session() to hold the browser open across multiple search() calls.
    """

    def __init__(
        self,
        rate_limit_seconds: float = 3.0,
        headless: bool = True,
    ) -> None:
        super().__init__(rate_limit_seconds)
        self._headless = headless
        self._ctx = None  # set by session() context manager

    @asynccontextmanager
    async def session(self):
        """Hold one browser + context open for the duration. Reused across search() calls."""
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._ctx = await browser.new_context(user_agent=_USER_AGENT)
            page = await self._ctx.new_page()
            await Stealth().apply_stealth_async(page)
            try:
                yield self
            finally:
                await self._ctx.close()
                await browser.close()
                self._ctx = None

    async def search(self, query: str, limit: int = 50) -> AsyncIterator[RawListing]:
        url = _SEARCH_URL.format(query=query.replace(" ", "+"))
        async for listing in self._scrape(url, limit):
            yield listing

    async def _scrape(self, url: str, limit: int) -> AsyncIterator[RawListing]:
        """Route to session-reuse path or standalone launch based on self._ctx."""
        if self._ctx:
            pages = self._ctx.pages
            page = pages[0] if pages else await self._ctx.new_page()
            async for listing in self._scrape_page(page, url, limit):
                yield listing
        else:
            from playwright.async_api import async_playwright
            from playwright_stealth import Stealth
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=self._headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                ctx = await browser.new_context(user_agent=_USER_AGENT)
                page = await ctx.new_page()
                await Stealth().apply_stealth_async(page)
                try:
                    async for listing in self._scrape_page(page, url, limit):
                        yield listing
                finally:
                    await ctx.close()
                    await browser.close()

    async def _scrape_page(self, page, url: str, limit: int) -> AsyncIterator[RawListing]:
        seen: set[str] = set()
        count = 0

        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await self._sleep()

        scroll_rounds = 0
        max_scrolls = max(6, (limit // 6) + 4)

        while count < limit and scroll_rounds < max_scrolls:
            listings = await self._extract_listings(page)
            for listing in listings:
                if listing.external_id in seen or count >= limit:
                    continue
                seen.add(listing.external_id)
                yield listing
                count += 1

            if count >= limit:
                break

            prev_seen = len(seen)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self._sleep()
            scroll_rounds += 1

            # Stop early if no new items appeared
            if scroll_rounds > 3 and len(seen) == prev_seen:
                break

    async def _extract_listings(self, page) -> list[RawListing]:
        # Primary: __NEXT_DATA__ JSON
        listings = await self._extract_from_next_data(page)
        if listings:
            return listings
        # Fallback: DOM scraping
        return await self._extract_from_dom(page)

    async def _extract_from_next_data(self, page) -> list[RawListing]:
        raw = await page.evaluate("""
            () => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.textContent : null;
            }
        """)
        if not raw:
            return []
        try:
            data = json.loads(raw)
            props = data.get("props", {}).get("pageProps", {})

            # Try multiple known paths in Mercari's Next.js data
            items = (
                props.get("items")
                or props.get("initialState", {}).get("search", {}).get("items")
                or props.get("searchResult", {}).get("items")
                or []
            )

            if not items:
                # Recursively scan for any list containing "id" and "name" and "price"
                items = _find_item_list(data)

            return [r for item in items if (r := _build_from_next_item(item))]
        except Exception:
            return []

    async def _extract_from_dom(self, page) -> list[RawListing]:
        """Fallback: extract from <a href="/item/{id}/"> listing cards."""
        try:
            cards = await page.query_selector_all('a[href*="/item/m"]')
            if not cards:
                # Try without the 'm' prefix (item IDs sometimes differ)
                cards = await page.query_selector_all('li[data-testid] a[href*="/item/"]')
        except Exception:
            return []

        results: list[RawListing] = []
        seen_hrefs: set[str] = set()

        for card in cards:
            try:
                href = await card.get_attribute("href") or ""
                if not href or href in seen_hrefs:
                    continue
                seen_hrefs.add(href)

                m = _ITEM_ID_RE.search(href)
                if not m:
                    continue
                item_id = m.group(1)

                text = (await card.inner_text()).strip()
                title, price = _parse_card_text(text)
                if not title or price is None or price <= 0:
                    continue

                full_url = (
                    f"https://www.mercari.com{href}"
                    if href.startswith("/")
                    else href
                )
                results.append(RawListing(
                    source="mercari",
                    external_id=item_id,
                    url=full_url,
                    title=title,
                    price=price,
                ))
            except Exception:
                continue

        return results


def _build_from_next_item(item: dict) -> Optional[RawListing]:
    try:
        item_id = str(item.get("id", "")).strip()
        name = (item.get("name") or item.get("title") or "").strip()
        if not item_id or not name:
            return None

        price_raw = item.get("price") or item.get("selling_price") or 0
        # Mercari stores prices as integers (cents) or floats (dollars)
        price = float(price_raw)
        if price > 10000:
            # Likely stored as cents → convert
            price = price / 100
        if price <= 0:
            return None

        # Status filter: skip sold items
        status = str(item.get("status") or item.get("item_status") or "").lower()
        if status in ("sold_out", "trading", "stop"):
            return None

        url = f"https://www.mercari.com/item/{item_id}/"
        return RawListing(
            source="mercari",
            external_id=item_id,
            url=url,
            title=name,
            price=price,
        )
    except (KeyError, ValueError, TypeError):
        return None


def _find_item_list(obj, depth: int = 0) -> list:
    """Recursively search the Next.js data tree for a list of item objects."""
    if depth > 8:
        return []
    if isinstance(obj, list) and len(obj) > 0:
        first = obj[0]
        if isinstance(first, dict) and ("name" in first or "title" in first) and "price" in first:
            return obj
    if isinstance(obj, dict):
        for v in obj.values():
            result = _find_item_list(v, depth + 1)
            if result:
                return result
    return []


def _parse_card_text(text: str) -> tuple[Optional[str], Optional[float]]:
    """
    Parse the inner text of a Mercari listing card.
    Card text is typically: "Item Title\n$150\nLikes: 3" or similar.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    price: Optional[float] = None
    price_idx: Optional[int] = None

    for i, line in enumerate(lines):
        m = _PRICE_RE.match(line)
        if m:
            try:
                price = float(m.group(1).replace(",", ""))
                price_idx = i
                break
            except ValueError:
                continue

    if price is None:
        return None, None

    non_price = [ln for i, ln in enumerate(lines) if i != price_idx]
    title = non_price[0] if non_price else None
    return title, price
