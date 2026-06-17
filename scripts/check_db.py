from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///data/hardware_scraper.db")
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT l.title, l.price, v.margin_pct, v.margin_tier, v.profit,
               v.ebay_median_price, v.ebay_comp_count, l.url
        FROM valuations v JOIN listings l ON l.id = v.listing_id
        ORDER BY v.margin_pct DESC
    """)).fetchall()
    print(f"All {len(rows)} valuations:\n")
    for r in rows:
        tier = r[3]
        profit = r[4]
        sign = "+" if profit >= 0 else ""
        print(f"[T{tier}] {sign}${profit:.0f} ({r[2]:.0f}%) | ask=${r[1]:.0f} ebay=${r[5]:.0f} ({r[6]} comps)")
        print(f"       {r[0][:70]}")
        print(f"       {r[7]}")
        print()
