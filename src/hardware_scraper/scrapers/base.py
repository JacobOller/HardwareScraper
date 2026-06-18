from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
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
        self._browser = None  # set by session() context manager in Playwright subclasses

    @asynccontextmanager
    async def session(self):
        """No-op session manager. Playwright scrapers override to hold a browser open."""
        yield self

    @abstractmethod
    async def search(self, query: str, limit: int = 50) -> AsyncIterator[RawListing]:
        ...

    async def browse(self, limit: int = 100) -> AsyncIterator[RawListing]:
        """Browse without a keyword. Override in scrapers that support it."""
        return
        yield  # make this an async generator

    async def _sleep(self) -> None:
        await asyncio.sleep(self._rate_limit)
