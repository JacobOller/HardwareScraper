from hardware_scraper.config import get_config
from hardware_scraper.valuation.calculator import ValuationCalculator

cfg = get_config()
print("platform:", cfg.fees.platform)
print("ebay_rate:", cfg.fees.ebay_rate)

calc = ValuationCalculator()
# PS5 with HDMI fault: asking $120, eBay working-used comp $320, console shipping $12
r = calc.calculate(asking_price=120, ebay_median=320, comp_count=8, category="console")
print("estimated_fees:", r.estimated_fees, "(", round(r.estimated_fees / 320 * 100, 1), "%)")
print("net_resale:", r.net_resale)
print("profit:", r.profit)
print("margin:", r.margin_pct, "%", r.margin_label)
