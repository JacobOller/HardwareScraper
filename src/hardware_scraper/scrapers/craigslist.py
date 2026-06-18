from __future__ import annotations

import re
from typing import AsyncIterator, Optional
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, RawListing

_ITEM_ID_RE = re.compile(r"/(\d{10})\.html")
_PRICE_RE = re.compile(r"\$([\d,]+)")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# CL returns ~120 results per page; increment offset by this amount
_PAGE_SIZE = 120


class CraigslistScraper(BaseScraper):
    """
    Craigslist scraper using httpx + BeautifulSoup (no browser needed — CL is server-rendered).

    search() searches /search/sss (for sale - general) with a keyword.
    browse() scrapes /search/eee (electronics - all) to surface local hardware without a keyword.
    Paginates via ?s=0, ?s=120, ?s=240, ... offsets.
    """

    def __init__(
        self,
        subdomain: str = "boston",
        zip_code: str = "",
        radius_miles: int = 40,
        rate_limit_seconds: float = 3.0,
    ) -> None:
        super().__init__(rate_limit_seconds)
        self._subdomain = subdomain
        self._zip = zip_code
        self._radius = radius_miles

    def _search_url(self, query: str, offset: int = 0) -> str:
        base = f"https://{self._subdomain}.craigslist.org/search/sss"
        return (
            f"{base}?query={quote_plus(query)}&postal={self._zip}"
            f"&search_distance={self._radius}&sort=date&s={offset}"
        )

    def _browse_url(self, offset: int = 0) -> str:
        base = f"https://{self._subdomain}.craigslist.org/search/eee"
        return f"{base}?postal={self._zip}&search_distance={self._radius}&sort=date&s={offset}"

    async def search(self, query: str, limit: int = 50) -> AsyncIterator[RawListing]:
        seen: set[str] = set()
        count = 0
        offset = 0
        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=20) as client:
            while count < limit:
                url = self._search_url(query, offset)
                page_listings = await self._fetch_page(client, url)
                if not page_listings:
                    break
                for listing in page_listings:
                    if listing.external_id in seen or count >= limit:
                        continue
                    seen.add(listing.external_id)
                    yield listing
                    count += 1
                if len(page_listings) < _PAGE_SIZE:
                    break
                offset += _PAGE_SIZE
                await self._sleep()

    async def browse(self, limit: int = 100) -> AsyncIterator[RawListing]:
        seen: set[str] = set()
        count = 0
        offset = 0
        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=20) as client:
            while count < limit:
                url = self._browse_url(offset)
                page_listings = await self._fetch_page(client, url)
                if not page_listings:
                    break
                for listing in page_listings:
                    if listing.external_id in seen or count >= limit:
                        continue
                    seen.add(listing.external_id)
                    yield listing
                    count += 1
                if len(page_listings) < _PAGE_SIZE:
                    break
                offset += _PAGE_SIZE
                await self._sleep()

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> list[RawListing]:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception:
            return []
        return _parse_page(resp.text)


def _parse_page(html: str) -> list[RawListing]:
    soup = BeautifulSoup(html, "html.parser")

    # New CL design (2024+): li.cl-search-result
    items = soup.select("li.cl-search-result")
    if items:
        return [r for item in items if (r := _parse_new(item))]

    # Old CL design fallback
    return [r for item in soup.select("li.result-row") if (r := _parse_old(item))]


def _parse_new(item) -> Optional[RawListing]:
    try:
        item_id = str(item.get("data-pid", "")).strip()
        link = item.select_one("a.cl-app-anchor, a.posting-title")
        if not link:
            return None
        href = link.get("href", "")
        if not item_id:
            m = _ITEM_ID_RE.search(href)
            item_id = m.group(1) if m else ""
        if not item_id:
            return None

        title_el = link.select_one(".label") or link
        title = title_el.get_text(strip=True)
        if not title:
            return None

        price_el = item.select_one("span.priceinfo")
        if not price_el:
            return None
        price = _parse_price(price_el.get_text())
        if price is None or price <= 0:
            return None

        loc_el = item.select_one("span.supertitle, .meta .maptag")
        location = loc_el.get_text(strip=True).strip("() ") if loc_el else None

        url = href if href.startswith("http") else f"https://craigslist.org{href}"
        return RawListing(
            source="craigslist",
            external_id=item_id,
            url=url,
            title=title,
            price=price,
            location=location,
        )
    except Exception:
        return None


def _parse_old(item) -> Optional[RawListing]:
    try:
        item_id = str(item.get("data-pid", "")).strip()
        link = item.select_one("a.result-title")
        if not link:
            return None
        href = link.get("href", "")
        if not item_id:
            m = _ITEM_ID_RE.search(href)
            item_id = m.group(1) if m else ""
        if not item_id:
            return None

        title = link.get_text(strip=True)
        if not title:
            return None

        price_el = item.select_one("span.result-price")
        if not price_el:
            return None
        price = _parse_price(price_el.get_text())
        if price is None or price <= 0:
            return None

        hood_el = item.select_one(".result-hood")
        location = hood_el.get_text(strip=True).strip("() ") if hood_el else None

        return RawListing(
            source="craigslist",
            external_id=item_id,
            url=href,
            title=title,
            price=price,
            location=location,
        )
    except Exception:
        return None


def _parse_price(text: str) -> Optional[float]:
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None
