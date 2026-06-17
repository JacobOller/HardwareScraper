import asyncio
import json
from playwright.async_api import async_playwright


async def debug():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir="data/browser_session",
            headless=False,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        # Category IDs from Apollo state:
        # 1   = Electronics & Media
        # 1.6 = Computers & Accessories
        # 1.5 = Video games & Consoles

        tests = [
            "https://offerup.com/search/?q=&category_id=1.6&radius=25&zipcode=02766",
            "https://offerup.com/search/?q=&category=1.6&radius=25&zipcode=02766",
            "https://offerup.com/search/?q=&categoryId=1.6&radius=25&zipcode=02766",
            "https://offerup.com/search/?q=&category_id=1&radius=25&zipcode=02766",
        ]

        for url in tests:
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await asyncio.sleep(1)
            raw = await page.evaluate("() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }")
            if raw:
                d = json.loads(raw)
                tiles = d.get("props", {}).get("pageProps", {}).get("searchFeedResponse", {}).get("looseTiles", [])
                listing_ct = sum(1 for t in tiles if t.get("tileType") == "LISTING")
                # Check what query OfferUp actually used (might be in the data)
                query_info = d.get("props", {}).get("pageProps", {}).get("searchFeedResponse", {}).get("query", "?")
                print(f"URL: {url}")
                print(f"  Listings: {listing_ct} | query field: {query_info!r}")
            else:
                print(f"URL: {url}")
                print("  No __NEXT_DATA__")

        await browser.close()


asyncio.run(debug())
