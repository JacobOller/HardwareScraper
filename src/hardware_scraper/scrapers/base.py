from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, List, Optional


@dataclass
class RawListing:
    source: str
    external_id: str
    url: str
    title: str
    price: float
    location: Optional[str] = None
    description: Optional[str] = None
    image_urls: List[str] = field(default_factory=list)
    posted_at: Optional[datetime] = None


class BaseScraper(ABC):
    def __init__(self, rate_limit_seconds: float = 3.0) -> None:
        self._rate_limit = rate_limit_seconds

    @abstractmethod
    async def search(self, query: str, limit: int = 50) -> AsyncIterator[RawListing]:
        ...

    async def _sleep(self) -> None:
        await asyncio.sleep(self._rate_limit)
