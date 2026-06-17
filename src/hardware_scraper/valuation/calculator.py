from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from hardware_scraper.config import get_config, MarginTiers


@dataclass
class ValuationResult:
    ebay_median_price: float
    ebay_comp_count: int
    estimated_fees: float
    estimated_shipping: float
    net_resale: float
    profit: float
    margin_pct: float
    margin_tier: int
    margin_label: str


_TIER_LABELS = {1: "Excellent", 2: "Good", 3: "Marginal", 4: "Low", 5: "Overpriced"}


class ValuationCalculator:
    """
    Computes profit margin from asking price and eBay comp data.

    Formula:
        net_resale  = median_ebay_sold - (median_ebay_sold * ebay_rate + ebay_fixed) - outbound_shipping
        profit      = net_resale - asking_price
        margin_pct  = (profit / asking_price) * 100

    Outbound shipping is looked up per product category from config.shipping.by_category.
    """

    def __init__(self) -> None:
        self._cfg = get_config()

    def calculate(
        self,
        asking_price: float,
        ebay_median: float,
        comp_count: int,
        category: Optional[str] = None,
    ) -> ValuationResult:
        fees = self._cfg.fees
        shipping = self._cfg.shipping.for_category(category)
        estimated_fees = ebay_median * fees.ebay_rate + fees.ebay_fixed
        net_resale = ebay_median - estimated_fees - shipping
        profit = net_resale - asking_price
        margin_pct = (profit / asking_price * 100) if asking_price > 0 else 0.0
        tier, label = self._classify(margin_pct)
        return ValuationResult(
            ebay_median_price=round(ebay_median, 2),
            ebay_comp_count=comp_count,
            estimated_fees=round(estimated_fees, 2),
            estimated_shipping=round(shipping, 2),
            net_resale=round(net_resale, 2),
            profit=round(profit, 2),
            margin_pct=round(margin_pct, 1),
            margin_tier=tier,
            margin_label=label,
        )

    def _classify(self, margin_pct: float) -> tuple[int, str]:
        t = self._cfg.margin_tiers
        if margin_pct >= t.excellent:
            return 1, _TIER_LABELS[1]
        if margin_pct >= t.good:
            return 2, _TIER_LABELS[2]
        if margin_pct >= t.marginal:
            return 3, _TIER_LABELS[3]
        if margin_pct >= t.low:
            return 4, _TIER_LABELS[4]
        return 5, _TIER_LABELS[5]
