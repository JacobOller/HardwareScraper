from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from hardware_scraper.config import get_config
from hardware_scraper.models import EbayComp
from .client import EbayClient


class CompFetcher:
    """Fetches eBay sold comps for a product and caches them in the DB."""

    def __init__(self, client: EbayClient, db: Session, scraper=None) -> None:
        self._client = client
        self._db = db
        self._cfg = get_config()
        self._scraper = scraper  # optional shared EbayScraper; avoids per-call browser launch

    def get_cached_comps(self, product_id: int, condition: str) -> Optional[List[EbayComp]]:
        cache_cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self._cfg.ebay.comps_cache_hours
        )
        comps = (
            self._db.query(EbayComp)
            .filter(
                EbayComp.product_id == product_id,
                EbayComp.condition == condition,
                EbayComp.fetched_at >= cache_cutoff,
            )
            .all()
        )
        return comps if comps else None

    async def fetch_and_cache(
        self, product_id: int, canonical_name: str, condition: str
    ) -> List[EbayComp]:
        cfg = self._cfg
        use_api = bool(cfg.ebay.app_id and cfg.ebay.cert_id)

        # For broken items, append keyword to narrow to the for-parts market.
        # eBay condition filter 7000 is also applied by the scraper for this condition.
        ebay_query = canonical_name
        if condition == "for_parts":
            ebay_query = f"{canonical_name} for parts"

        if use_api:
            raw = await self._client.get_sold_listings(
                query=ebay_query,
                days_back=cfg.ebay.comps_days_back,
                limit=cfg.ebay.max_comps_per_query,
                condition=condition,
            )
            comps = [_comp_from_api(item, product_id, condition) for item in raw]
        else:
            from .scraper import EbayScraper
            scraper = self._scraper if self._scraper is not None else EbayScraper()
            raw = await scraper.get_sold_listings(
                query=ebay_query,
                limit=cfg.ebay.max_comps_per_query,
                condition=condition,
            )
            comps = [_comp_from_scraper(item, product_id, condition) for item in raw]

        comps = [c for c in comps if c is not None]
        for comp in comps:
            self._db.add(comp)
        self._db.commit()
        return comps

    def median_sold_price(self, comps: List[EbayComp]) -> Tuple[float, int]:
        """Returns (median_price, comp_count) after IQR outlier removal."""
        if not comps:
            return 0.0, 0

        prices = sorted(c.sold_price for c in comps)
        if len(prices) >= 4:
            q1 = statistics.quantiles(prices, n=4)[0]
            q3 = statistics.quantiles(prices, n=4)[2]
            iqr = q3 - q1
            prices = [p for p in prices if q1 - 1.5 * iqr <= p <= q3 + 1.5 * iqr]

        if not prices:
            return 0.0, 0

        return statistics.median(prices), len(prices)


def _comp_from_api(item: dict, product_id: int, condition: str) -> Optional[EbayComp]:
    try:
        price = float(item["price"]["value"])
        shipping = 0.0
        if item.get("shippingOptions"):
            sc = item["shippingOptions"][0].get("shippingCost", {})
            shipping = float(sc.get("value", 0))
        sold_date = datetime.fromisoformat(
            item.get("itemEndDate", datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
        )
        return EbayComp(
            product_id=product_id,
            condition=condition,
            sold_price=price,
            shipping=shipping,
            ebay_item_id=item.get("itemId", ""),
            sold_date=sold_date,
        )
    except (KeyError, ValueError, TypeError):
        return None


def _comp_from_scraper(item: dict, product_id: int, condition: str) -> Optional[EbayComp]:
    try:
        return EbayComp(
            product_id=product_id,
            condition=condition,
            sold_price=item["sold_price"],
            shipping=item["shipping"],
            ebay_item_id=item["ebay_item_id"],
            sold_date=item["sold_date"],
        )
    except (KeyError, ValueError, TypeError):
        return None
