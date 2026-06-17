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
        await page.goto(
            "https://offerup.com/search/?q=laptop&radius=25&zipcode=02766",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(3)

        # Get the actual href from listing links in the DOM
        hrefs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href*="/item/"]'))
                       .slice(0, 5)
                       .map(a => a.href)
        """)
        print("Actual OfferUp listing hrefs from DOM:")
        for h in hrefs:
            print(f"  {h}")

        # Also check what listingId looks like vs the URL slug
        raw = await page.evaluate("() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }")
        if raw:
            data = json.loads(raw)
            tiles = data["props"]["pageProps"]["searchFeedResponse"]["looseTiles"]
            listings = [t for t in tiles if t.get("tileType") == "LISTING"][:3]
            print("\n__NEXT_DATA__ listingId values:")
            for t in listings:
                lid = t.get("listing", {}).get("listingId")
                print(f"  {lid}")

        await browser.close()


asyncio.run(debug())
