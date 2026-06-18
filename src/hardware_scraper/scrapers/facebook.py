from __future__ import annotations

import json
import re
from datetime import datetime
from typing import AsyncIterator, Optional

from .base import BaseScraper, RawListing

_SEARCH_BASE = "https://www.facebook.com/marketplace/search/"
_ITEM_URL = "https://www.facebook.com/marketplace/item/{item_id}/"

# FB item IDs in URLs
_ITEM_ID_RE = re.compile(r"/marketplace/item/(\d+)")
# Price: "$150", "$1,200"
_PRICE_RE = re.compile(r"\$([\d,]+)")


class FacebookMarketplaceScraper(BaseScraper):
    """
    Playwright-based Facebook Marketplace scraper using a persistent browser session.

    FB embeds listing data in multiple <script type="application/json"> tags as
    Relay store JSON. We scan those first; if the structure has changed we fall
    back to scraping the DOM card links directly.

    First-time setup: run with headless=False so you can log in manually.
    The session cookie is then persisted and subsequent runs work headlessly.
    """

    def __init__(
        self,
        session_dir: str = "data/facebook_session",
        rate_limit_seconds: float = 3.0,
        headless: bool = True,
        latitude: float = 0.0,
        longitude: float = 0.0,
        radius_miles: int = 40,
        city_marketplace_url: str = "",
    ) -> None:
        super().__init__(rate_limit_seconds)
        self._session_dir = session_dir
        self._headless = headless
        self._latitude = latitude
        self._longitude = longitude
        self._radius_miles = radius_miles
        self._city_marketplace_url = city_marketplace_url

    def _loc_params(self) -> str:
        """Return location query-string fragment if coordinates are configured."""
        if self._latitude and self._longitude:
            return (
                f"&latitude={self._latitude}&longitude={self._longitude}"
                f"&radius={self._radius_miles}&radiusUnit=mi"
            )
        return ""

    async def search(self, query: str, limit: int = 50) -> AsyncIterator[RawListing]:
        q = query.replace(" ", "+")
        if self._city_marketplace_url:
            # Anchor keyword search to the configured city — lat/lon params are ignored by FB.
            # URL format: facebook.com/marketplace/{city_id_or_slug}/search/?query=...
            base = self._city_marketplace_url.rstrip("/")
            url = f"{base}/search/?query={q}&exact=false"
        else:
            url = f"{_SEARCH_BASE}?query={q}&exact=false{self._loc_params()}"
        async for listing in self._scrape(url, limit):
            yield listing

    async def browse(self, limit: int = 100) -> AsyncIterator[RawListing]:
        # If a city-specific URL is configured, use it — it locks to the correct geographic area
        # regardless of the session's stored account location (URL params are often ignored by FB).
        if self._city_marketplace_url:
            url = self._city_marketplace_url
        else:
            url = f"{_SEARCH_BASE}?query=&exact=false{self._loc_params()}"
        async for listing in self._scrape(url, limit):
            yield listing

    async def _scrape(self, url: str, limit: int) -> AsyncIterator[RawListing]:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch_persistent_context(
                user_data_dir=self._session_dir,
                headless=self._headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await self._sleep()

            seen_ids: set[str] = set()
            count = 0
            scroll_rounds = 0
            # ~6-8 items load per scroll; add extra rounds as buffer
            max_scrolls = max(8, (limit // 6) + 4)

            while count < limit and scroll_rounds < max_scrolls:
                listings = await self._extract_listings(page)
                for raw in listings:
                    if raw.external_id in seen_ids:
                        continue
                    seen_ids.add(raw.external_id)
                    yield raw
                    count += 1
                    if count >= limit:
                        break

                if count >= limit:
                    break

                prev_count = len(seen_ids)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self._sleep()
                scroll_rounds += 1

                # Stop early if no new items appeared after scrolling
                new_after_scroll = await self._extract_listings(page)
                new_ids = {r.external_id for r in new_after_scroll} - seen_ids
                if not new_ids and scroll_rounds > 3:
                    break

            await browser.close()

    async def _extract_listings(self, page) -> list[RawListing]:
        # Primary: scan embedded Relay JSON blobs in <script> tags
        json_listings = await self._extract_from_scripts(page)
        if json_listings:
            return json_listings

        # Fallback: DOM card links
        return await self._extract_from_dom(page)

    async def _extract_from_scripts(self, page) -> list[RawListing]:
        """
        FB Marketplace embeds listing data in <script type="application/json"> tags
        as Relay store JSON. Each page can contain many such tags; we scan them all
        looking for objects that contain marketplace listing fields.
        """
        try:
            blobs: list[str] = await page.evaluate("""
                () => {
                    const scripts = Array.from(
                        document.querySelectorAll('script[type="application/json"]')
                    );
                    return scripts
                        .map(s => s.textContent || "")
                        .filter(t => t.includes("marketplace_listing_title") ||
                                     t.includes("listing_price"));
                }
            """)
        except Exception:
            return []

        results: list[RawListing] = []
        seen: set[str] = set()
        for blob in blobs:
            try:
                data = json.loads(blob)
                self._find_listings_in_json(data, results, seen)
            except (json.JSONDecodeError, Exception):
                continue
        return results

    def _find_listings_in_json(
        self,
        obj,
        results: list[RawListing],
        seen: set[str],
        depth: int = 0,
    ) -> None:
        if depth > 20 or len(results) > 300:
            return

        if isinstance(obj, dict):
            if "marketplace_listing_title" in obj and "listing_price" in obj:
                raw = self._build_from_relay_listing(obj)
                if raw and raw.external_id not in seen:
                    seen.add(raw.external_id)
                    results.append(raw)
                return
            for value in obj.values():
                self._find_listings_in_json(value, results, seen, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                self._find_listings_in_json(item, results, seen, depth + 1)

    def _build_from_relay_listing(self, listing: dict) -> Optional[RawListing]:
        try:
            item_id = str(listing.get("id", "")).strip()
            title = (listing.get("marketplace_listing_title") or "").strip()

            price_data = listing.get("listing_price") or {}
            amount_str = str(price_data.get("amount") or price_data.get("formatted_amount") or "0")
            # Strip currency symbols / commas
            price = float(re.sub(r"[^\d.]", "", amount_str) or "0")

            if not item_id or not title or price <= 0:
                return None

            # Location
            location: Optional[str] = None
            loc = listing.get("location") or {}
            rgc = loc.get("reverse_geocode") or {}
            city = rgc.get("city") or rgc.get("short_name") or ""
            state = rgc.get("state_abbreviated") or ""
            if city:
                location = f"{city}, {state}".strip(", ")

            # Thumbnail
            photo = listing.get("primary_listing_photo") or {}
            img = photo.get("image") or {}
            img_url: Optional[str] = img.get("uri")

            return RawListing(
                source="facebook",
                external_id=item_id,
                url=_ITEM_URL.format(item_id=item_id),
                title=title,
                price=price,
                location=location or None,
                image_urls=[img_url] if img_url else [],
            )
        except (KeyError, ValueError, TypeError):
            return None

    async def _extract_from_dom(self, page) -> list[RawListing]:
        """
        Fallback DOM scraper.  FB listing cards are <a href="/marketplace/item/{id}/"> links.
        We pull the href for the ID and parse the card's inner text for price, title, location.
        """
        try:
            cards = await page.query_selector_all('a[href*="/marketplace/item/"]')
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

                id_match = _ITEM_ID_RE.search(href)
                if not id_match:
                    continue
                item_id = id_match.group(1)

                text = (await card.inner_text()).strip()
                img_el = await card.query_selector("img")
                img_url = await img_el.get_attribute("src") if img_el else None

                title, price, location = _parse_card_text(text)
                if not title or price is None:
                    continue

                results.append(RawListing(
                    source="facebook",
                    external_id=item_id,
                    url=_ITEM_URL.format(item_id=item_id),
                    title=title,
                    price=price,
                    location=location,
                    image_urls=[img_url] if img_url else [],
                ))
            except Exception:
                continue

        return results


def _parse_card_text(text: str) -> tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Parse the raw inner text of a FB listing card.

    FB card text is typically ordered as:
        "$150\nRTX 3080\nAttleboro, MA"
    or sometimes:
        "RTX 3080\n$150\nAttleboro, MA"

    We find the price line by the $ prefix, treat the next non-price line as
    the title, and an optional trailing line as the location.
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
        return None, None, None

    non_price = [ln for i, ln in enumerate(lines) if i != price_idx]
    title = non_price[0] if non_price else None
    location = non_price[1] if len(non_price) > 1 else None

    # Ignore "Free" / "$0" listings
    if price == 0:
        return None, None, None

    return title, price, location
