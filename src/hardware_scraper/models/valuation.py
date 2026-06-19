from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Boolean
from .base import Base


class EbayComp(Base):
    __tablename__ = "ebay_comps"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    condition: Mapped[str] = mapped_column(String(32))          # "used", "like_new", "for_parts"
    sold_price: Mapped[float] = mapped_column(Float)
    shipping: Mapped[float] = mapped_column(Float, default=0.0)
    ebay_item_id: Mapped[str] = mapped_column(String(64))
    sold_date: Mapped[datetime] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Valuation(Base):
    __tablename__ = "valuations"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    ebay_median_price: Mapped[float] = mapped_column(Float)
    ebay_comp_count: Mapped[int] = mapped_column(Integer)
    estimated_fees: Mapped[float] = mapped_column(Float)
    estimated_shipping: Mapped[float] = mapped_column(Float)
    net_resale: Mapped[float] = mapped_column(Float)
    profit: Mapped[float] = mapped_column(Float)
    margin_pct: Mapped[float] = mapped_column(Float)
    margin_tier: Mapped[int] = mapped_column(Integer)           # 1–5
    margin_label: Mapped[str] = mapped_column(String(32))       # Excellent, Good, etc.
    inbound_shipping: Mapped[float] = mapped_column(Float, default=0.0)
    amazon_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    valuated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
