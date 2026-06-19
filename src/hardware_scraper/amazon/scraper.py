"""Amazon active listing price scraper.

Uses Playwright + stealth to search Amazon for a product and return the current
market price. Supplements eBay sold comps with real-time sell-side data on
the actual resale platform (Amazon).

Amazon is more aggressively anti-bot than eBay. This scraper:
- Uses a persistent session at data/amazon_session/ to retain cookies
- Applies playwright-stealth to mask automation signals
- Parses the buy-box price from search results (the price Amazon shows for top result)
- Falls back to None if blocked or no reliable price found

Enable with amazon.enabled: true in config.yaml.
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Optional

from bs4 import BeautifulSoup

_SEARCH_BASE = "https://www.amazon.com/s"
_SESSION_DIR = "data/amazon_session"
_PRICE_RE = re.compile(r"\$([\d,]+\.?\d*)")


class AmazonScraper:
    """
    Fetches the current active Amazon listing price for a search query.

    Supports both standalone and shared-session (session() context manager) modes,
    matching the pattern used by EbayScraper.
    """

    def __init__(self, context=None, rate_limit_seconds: float = 5.0) -> None:
        self._context = context
        self._rate_limit = rate_limit_seconds

    @classmethod
    @asynccontextmanager
    async def session(cls, session_dir: str = _SESSION_DIR, rate_limit_seconds: float = 5.0):
        """Open one persistent browser context and yield a shared AmazonScraper."""
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=session_dir,
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                yield cls(context=ctx, rate_limit_seconds=rate_limit_seconds)
            finally:
                await ctx.close()

    async def get_price(self, query: str) -> Optional[float]:
        """
        Search Amazon for query and return the buy-box price of the top result.
        Returns None if Amazon blocks the request or no price can be parsed.
        """
        from playwright_stealth import Stealth

        url = f"{_SEARCH_BASE}?k={query.replace(' ', '+')}&s=review-rank"

        if self._context is not None:
            page = await self._context.new_page()
            try:
                await Stealth().apply_stealth_async(page)
                return await self._scrape_price(page, url)
            finally:
                await page.close()
        else:
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                ctx = await pw.chromium.launch_persistent_context(
                    user_data_dir=_SESSION_DIR,
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await Stealth().apply_stealth_async(page)
                try:
                    result = await self._scrape_price(page, url)
                finally:
                    await ctx.close()
                return result

    async def _scrape_price(self, page, url: str) -> Optional[float]:
        import asyncio
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(int(self._rate_limit * 1000))
        except Exception:
            return None

        html = await page.content()

        # Detect CAPTCHA / bot block
        if _is_blocked(html):
            return None

        return _parse_search_price(html)


def _is_blocked(html: str) -> bool:
    """Return True if Amazon returned a CAPTCHA or robot-check page."""
    lower = html.lower()
    return (
        "robot check" in lower
        or "captcha" in lower
        or "sorry, we just need to make sure you're not a robot" in lower
        or "enter the characters you see below" in lower
    )


def _parse_search_price(html: str) -> Optional[float]:
    """
    Extract the price from the first sponsored or organic Amazon search result.

    Amazon's search result HTML is complex. We try several selectors in order:
    1. Whole-dollar span next to a cents span (the split price pattern)
    2. The a-price-whole + a-price-fraction pattern
    3. Any visible price-like text in a result card
    """
    soup = BeautifulSoup(html, "html.parser")

    # Try the standard a-price layout: span.a-price > span.a-offscreen (full price as text)
    for offscreen in soup.select("span.a-price span.a-offscreen"):
        text = offscreen.get_text(strip=True)
        price = _parse_price(text)
        if price and price > 5.0:
            return price

    # Fallback: a-price-whole + a-price-fraction
    whole = soup.select_one("span.a-price-whole")
    frac = soup.select_one("span.a-price-fraction")
    if whole:
        try:
            dollars = float(whole.get_text(strip=True).replace(",", "").rstrip("."))
            cents = float(frac.get_text(strip=True)) / 100 if frac else 0.0
            return round(dollars + cents, 2)
        except (ValueError, AttributeError):
            pass

    return None


def _parse_price(text: str) -> Optional[float]:
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None
