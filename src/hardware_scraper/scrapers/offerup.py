from __future__ import annotations

import json
import re
from datetime import datetime
from typing import AsyncIterator, Optional

from .base import BaseScraper, RawListing


_OFFERUP_SEARCH_URL = "https://offerup.com/search/?q={query}&radius={radius}&zipcode={zip}"
# Empty-query URL surfaces all local listings. OfferUp ignores category_id params
# on the search endpoint; /cat/* pages use Apollo state with no listing data.
_OFFERUP_BROWSE_URL = "https://offerup.com/search/?q=&radius={radius}&zipcode={zip}"


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

            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
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

    async def browse(self, limit: int = 100) -> AsyncIterator[RawListing]:
        """Fetch all local listings using an empty-query search (no keyword needed)."""
        from playwright.async_api import async_playwright

        url = _OFFERUP_BROWSE_URL.format(radius=self._radius, zip=self._zip)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch_persistent_context(
                user_data_dir=self._session_dir,
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
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
            page_props = data.get("props", {}).get("pageProps", {})

            # Current structure (2024+): searchFeedResponse.looseTiles
            feed_response = page_props.get("searchFeedResponse", {})
            tiles = feed_response.get("looseTiles", [])

            if tiles:
                return self._parse_loose_tiles(tiles)

            # Legacy fallback: initialProps.searchResults path
            tiles = (
                page_props.get("initialProps", {})
                          .get("searchResults", {})
                          .get("data", {})
                          .get("search", {})
                          .get("feed", {})
                          .get("tiles", [])
            )
            if tiles:
                return self._parse_legacy_tiles(tiles)

        except (json.JSONDecodeError, AttributeError):
            pass

        return await self._extract_listings_dom(page)

    def _parse_loose_tiles(self, tiles: list) -> list[RawListing]:
        results = []
        for tile in tiles:
            if tile.get("tileType") != "LISTING":
                continue
            listing = tile.get("listing", {})
            try:
                image_url = listing.get("image", {}).get("url")
                results.append(RawListing(
                    source="offerup",
                    external_id=str(listing["listingId"]),
                    url=f"https://offerup.com/item/detail/{listing['listingId']}",
                    title=listing["title"],
                    price=float(listing["price"]),
                    location=listing.get("locationName"),
                    description=listing.get("conditionText"),
                    image_urls=[image_url] if image_url else [],
                    posted_at=None,
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return results

    def _parse_legacy_tiles(self, tiles: list) -> list[RawListing]:
        results = []
        for tile in tiles:
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
            await page.wait_for_load_state("domcontentloaded")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
