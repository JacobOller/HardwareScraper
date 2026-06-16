from typing import Optional
from sqlalchemy import String, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(64))          # "gpu", "cpu", "ram", etc.
    brand: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    canonical_name: Mapped[str] = mapped_column(String(256), unique=True)  # eBay search key
    specs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)     # {"vram_gb": 8, ...}


class ListingProduct(Base):
    __tablename__ = "listing_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    confidence: Mapped[float] = mapped_column(Float)           # 0.0–1.0
    condition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # "used", "for_parts", "like_new"
