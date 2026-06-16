from __future__ import annotations

import json
import re
from datetime import datetime
from typing import AsyncIterator, Optional

from .base import BaseScraper, RawListing


_OFFERUP_SEARCH_URL = "https://offerup.com/search/?q={query}&radius={radius}&zipcode={zip}"


class OfferUpScraper(BaseScraper):
    """
    Playwright-based OfferUp scraper using a persistent browser session.

    OfferUp renders listings as JSON embedded in a __NEXT_DATA__ script tag,
    which is faster than DOM scraping and survives minor layout changes.
    """

    def __init__(
        self,
        session_dir: str = "data/browser_session",
        zip_code: str = "",
        radius_miles: int = 25,
        rate_limit_seconds: float = 3.0,
        headless: bool = True,
    ) -> None:
        super().__init__(rate_limit_seconds)
        self._session_dir = session_dir
        self._zip = zip_code
        self._radius = radius_miles
        self._headless = headless

    async def search(self, query: str, limit: int = 50) -> AsyncIterator[RawListing]:
        from playwright.async_api import async_playwright

        url = _OFFERUP_SEARCH_URL.format(
            query=query.replace(" ", "+"),
            radius=self._radius,
            zip=self._zip,
        )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch_persistent_context(
                user_data_dir=self._session_dir,
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()

            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await self._sleep()

            count = 0
            while count < limit:
                listings = await self._extract_listings(page)
                for listing in listings:
                    if count >= limit:
                        break
                    yield listing
                    count += 1

                if count >= limit or not await self._has_next_page(page):
                    break

                await self._click_next_page(page)
                await self._sleep()

            await browser.close()

    async def _extract_listings(self, page) -> list[RawListing]:
        raw_json = await page.evaluate("""
            () => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.textContent : null;
            }
        """)

        if not raw_json:
            return await self._extract_listings_dom(page)

        try:
            data = json.loads(raw_json)
            items = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("initialProps", {})
                    .get("searchResults", {})
                    .get("data", {})
                    .get("search", {})
                    .get("feed", {})
                    .get("tiles", [])
            )
        except (json.JSONDecodeError, AttributeError):
            return await self._extract_listings_dom(page)

        results = []
        for tile in items:
            listing = tile.get("listing") or tile
            try:
                results.append(RawListing(
                    source="offerup",
                    external_id=str(listing["id"]),
                    url=f"https://offerup.com/item/detail/{listing['id']}",
                    title=listing["title"],
                    price=float(listing["price"]),
                    location=listing.get("location", {}).get("city"),
                    description=listing.get("description"),
                    image_urls=[listing["images"][0]["url"]] if listing.get("images") else [],
                    posted_at=_parse_dt(listing.get("utcUpdatedPayload")),
                ))
            except (KeyError, TypeError, ValueError):
                continue

        return results

    async def _extract_listings_dom(self, page) -> list[RawListing]:
        """Fallback: scrape listing cards from the DOM if __NEXT_DATA__ is absent."""
        cards = await page.query_selector_all("[data-testid='listing-card']")
        results = []
        for card in cards:
            try:
                title_el = await card.query_selector("[data-testid='listing-title']")
                price_el = await card.query_selector("[data-testid='listing-price']")
                link_el = await card.query_selector("a")
                if not (title_el and price_el and link_el):
                    continue
                title = await title_el.inner_text()
                price_text = await price_el.inner_text()
                href = await link_el.get_attribute("href") or ""
                price = float(re.sub(r"[^\d.]", "", price_text) or "0")
                id_match = re.search(r"/item/detail/(\d+)", href)
                if not id_match:
                    continue
                results.append(RawListing(
                    source="offerup",
                    external_id=id_match.group(1),
                    url=f"https://offerup.com{href}",
                    title=title.strip(),
                    price=price,
                ))
            except Exception:
                continue
        return results

    async def _has_next_page(self, page) -> bool:
        return await page.query_selector("[aria-label='Next page']") is not None

    async def _click_next_page(self, page) -> None:
        btn = await page.query_selector("[aria-label='Next page']")
        if btn:
            await btn.click()
            await page.wait_for_load_state("networkidle")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
