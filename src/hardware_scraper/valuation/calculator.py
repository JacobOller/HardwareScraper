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
    inbound_shipping: float
    net_resale: float
    profit: float
    margin_pct: float
    margin_tier: int
    margin_label: str
    amazon_price: Optional[float] = None


_TIER_LABELS = {1: "Excellent", 2: "Good", 3: "Marginal", 4: "Low", 5: "Overpriced"}


class ValuationCalculator:
    """
    Computes profit margin from asking price and eBay comp data.

    eBay sold listings are used for price discovery only. Fees are Amazon FBM (individual seller):
        estimated_fees = median_ebay_sold * amazon_referral_rate + amazon_per_item_fee
        net_resale     = median_ebay_sold - estimated_fees - outbound_shipping
        profit         = net_resale - asking_price
        margin_pct     = (profit / asking_price) * 100

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
        inbound_shipping: float = 0.0,
        amazon_price: Optional[float] = None,
    ) -> ValuationResult:
        fees = self._cfg.fees
        outbound_shipping = self._cfg.shipping.for_category(category)
        # Use Amazon active price as primary reference when available; eBay median as fallback
        resale_ref = amazon_price if (amazon_price and amazon_price > 0) else ebay_median
        estimated_fees = resale_ref * fees.amazon_referral_rate + fees.amazon_per_item_fee
        net_resale = resale_ref - estimated_fees - outbound_shipping
        profit = net_resale - asking_price - inbound_shipping
        margin_pct = (profit / asking_price * 100) if asking_price > 0 else 0.0
        tier, label = self._classify(margin_pct)
        return ValuationResult(
            ebay_median_price=round(ebay_median, 2),
            ebay_comp_count=comp_count,
            estimated_fees=round(estimated_fees, 2),
            estimated_shipping=round(outbound_shipping, 2),
            inbound_shipping=round(inbound_shipping, 2),
            net_resale=round(net_resale, 2),
            profit=round(profit, 2),
            margin_pct=round(margin_pct, 1),
            margin_tier=tier,
            margin_label=label,
            amazon_price=round(amazon_price, 2) if amazon_price else None,
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
