import pytest
from unittest.mock import patch, MagicMock

from hardware_scraper.valuation.calculator import ValuationCalculator


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.fees.ebay_rate = 0.1325
    cfg.fees.ebay_fixed = 0.30
    cfg.fees.outbound_shipping = 15.00
    cfg.shipping.for_category.return_value = 15.00
    cfg.margin_tiers.excellent = 50
    cfg.margin_tiers.good = 30
    cfg.margin_tiers.marginal = 15
    cfg.margin_tiers.low = 0
    return cfg


@pytest.fixture
def calculator(mock_config):
    with patch("hardware_scraper.valuation.calculator.get_config", return_value=mock_config):
        yield ValuationCalculator()


class TestValuationCalculator:
    def test_profit_calculation(self, calculator):
        result = calculator.calculate(asking_price=100.0, ebay_median=200.0, comp_count=10)
        expected_fees = 200.0 * 0.1325 + 0.30
        expected_net = 200.0 - expected_fees - 15.00
        assert abs(result.net_resale - expected_net) < 0.01
        assert abs(result.profit - (expected_net - 100.0)) < 0.01

    def test_margin_pct(self, calculator):
        result = calculator.calculate(asking_price=100.0, ebay_median=200.0, comp_count=5)
        assert result.margin_pct > 0

    def test_excellent_tier(self, calculator):
        result = calculator.calculate(asking_price=50.0, ebay_median=300.0, comp_count=15)
        assert result.margin_tier == 1
        assert result.margin_label == "Excellent"

    def test_overpriced_tier(self, calculator):
        result = calculator.calculate(asking_price=500.0, ebay_median=200.0, comp_count=5)
        assert result.margin_tier == 5
        assert result.margin_label == "Overpriced"
        assert result.profit < 0

    def test_zero_asking_price(self, calculator):
        result = calculator.calculate(asking_price=0.0, ebay_median=100.0, comp_count=5)
        assert result.margin_pct == 0.0
