from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///data/hardware_scraper.db")
with engine.connect() as conn:
    conn.execute(text("DELETE FROM ebay_comps"))
    conn.execute(text("DELETE FROM valuations"))
    conn.commit()
    count = conn.execute(text("SELECT COUNT(*) FROM listings WHERE status = 'identified'")).scalar()
    print(f"Cleared. Listings ready to valuate: {count}")
