from sqlalchemy import create_engine, text

engine = create_engine("sqlite:///data/hardware_scraper.db")
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM listings")).scalar()
    by_status = conn.execute(text("SELECT status, COUNT(*) FROM listings GROUP BY status")).fetchall()
    print(f"Total listings: {total}")
    for row in by_status:
        print(f"  {row[0]}: {row[1]}")

    print()
    rows = conn.execute(text("SELECT title, price, status FROM listings WHERE status='new' LIMIT 15")).fetchall()
    print(f"Sample unidentified listings (status=new):")
    for r in rows:
        print(f"  ${r[1]:.0f}  {r[0][:70]}")
