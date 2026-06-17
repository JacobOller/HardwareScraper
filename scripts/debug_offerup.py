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
        url = "https://offerup.com/search/?q=RTX+3080&radius=25&zipcode=02766"
        await page.goto(url, wait_until="networkidle", timeout=30000)

        raw = await page.evaluate("""
            () => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.textContent : null;
            }
        """)

        data = json.loads(raw)
        tiles = data["props"]["pageProps"]["searchFeedResponse"]["looseTiles"]
        print(f"Total tiles: {len(tiles)}")
        print()

        # Print first 3 tiles in full
        for i, tile in enumerate(tiles[:3]):
            print(f"--- Tile {i} ---")
            print(json.dumps(tile, indent=2))
            print()

        await browser.close()


asyncio.run(debug())
