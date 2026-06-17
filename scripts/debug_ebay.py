import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup


async def debug():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir="data/ebay_session",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await Stealth().apply_stealth_async(page)

        url = "https://www.ebay.com/sch/i.html?_nkw=RTX+3080&LH_Sold=1&LH_Complete=1&_sacat=0&LH_ItemCondition=3000"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        items = [li for li in soup.select(".srp-results li") if "s-card" in (li.get("class") or [])]
        print(f"s-card items: {len(items)}")

        # For first 3 items, print ALL text content and ALL class names found inside
        for i, item in enumerate(items[:3]):
            listing_id = item.get("data-listingid", "?")
            print(f"\n=== Item {i} | listing id: {listing_id} ===")
            # Print all tags with their classes and text
            for tag in item.find_all(True):
                classes = tag.get("class", [])
                text = tag.get_text(strip=True)
                if text and len(text) < 100 and classes:
                    print(f"  <{tag.name} class='{' '.join(classes)}'> = {text!r}")

        await browser.close()


asyncio.run(debug())
