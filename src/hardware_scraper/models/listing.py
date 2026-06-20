from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_listing_source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))           # "offerup", "facebook"
    external_id: Mapped[str] = mapped_column(String(128))     # platform's own ID
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    price: Mapped[float] = mapped_column(Float)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_urls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(32), default="new")  # new, identified, valuated, skipped
    saved: Mapped[bool] = mapped_column(default=False)
    hidden: Mapped[bool] = mapped_column(default=False)
    is_local_pickup: Mapped[bool] = mapped_column(default=True)  # False = ships to buyer; eBay Local only
    bought_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    bought_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sold_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
