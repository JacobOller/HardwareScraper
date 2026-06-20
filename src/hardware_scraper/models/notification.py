from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    channel: Mapped[str] = mapped_column(String(32), default="discord")
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    margin_pct_at_send: Mapped[float] = mapped_column(Float)
    ai_verdict: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON blob
