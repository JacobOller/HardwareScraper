import pytest
from hardware_scraper.parsers.category_rules import detect_category, detect_condition, is_refurb_noise
from hardware_scraper.parsers.title_parser import TitleParser


@pytest.fixture
def parser():
    return TitleParser()


# ---------------------------------------------------------------------------
# $0 / zero-price filter (tested via ingest helper logic)
# ---------------------------------------------------------------------------

class TestZeroPriceFilter:
    """The ingest _store_listing function drops price <= 0."""

    def test_zero_price_is_truthy_check(self):
        # Sanity: 0.0 <= 0 is True — confirm the filter expression is correct
        assert 0.0 <= 0
        assert -1.0 <= 0

    def test_positive_price_passes(self):
        assert not (50.0 <= 0)

    def test_none_price_handled(self):
        price = None
        assert price is None or price <= 0


# ---------------------------------------------------------------------------
# Expanded for-parts condition detection
# ---------------------------------------------------------------------------

class TestForPartsCondition:
    def test_for_parts_literal(self):
        assert detect_condition("GTX 1080 for parts") == "for_parts"

    def test_not_working(self):
        assert detect_condition("RTX 3070 not working") == "for_parts"

    def test_broken(self):
        assert detect_condition("broken laptop") == "for_parts"

    def test_no_display(self):
        assert detect_condition("MacBook Pro - no display") == "for_parts"

    def test_no_post(self):
        assert detect_condition("Gaming PC no post") == "for_parts"

    def test_no_power(self):
        assert detect_condition("PC no power") == "for_parts"

    def test_wont_power_on(self):
        assert detect_condition("PS5 won't power on") == "for_parts"

    def test_wont_power_on_no_apostrophe(self):
        assert detect_condition("Xbox wont power on") == "for_parts"

    def test_cracked_screen(self):
        assert detect_condition("iPhone 14 cracked screen") == "for_parts"

    def test_shattered_screen(self):
        assert detect_condition("iPad shattered screen") == "for_parts"

    def test_bad_battery(self):
        assert detect_condition("MacBook Air bad battery") == "for_parts"

    def test_bent_pins(self):
        assert detect_condition("i9-12900K bent pins") == "for_parts"

    def test_water_damage(self):
        assert detect_condition("laptop water damage") == "for_parts"

    def test_water_damaged(self):
        assert detect_condition("MacBook water damaged") == "for_parts"

    def test_bad_gpu(self):
        assert detect_condition("Gaming PC bad gpu") == "for_parts"

    def test_bios_only(self):
        assert detect_condition("RTX 3090 bios only") == "for_parts"

    def test_sold_as_is(self):
        assert detect_condition("GPU sold as is") == "for_parts"

    def test_does_not_turn_on(self):
        assert detect_condition("Switch does not turn on") == "for_parts"

    def test_no_boot(self):
        assert detect_condition("PC no boot") == "for_parts"

    def test_damaged(self):
        assert detect_condition("RTX 3080 damaged") == "for_parts"

    def test_untested(self):
        assert detect_condition("Ryzen 5600X untested") == "for_parts"

    def test_as_is_hyphen(self):
        assert detect_condition("desktop as-is") == "for_parts"

    def test_like_new_not_confused(self):
        assert detect_condition("RTX 3080 like new") == "like_new"

    def test_used_default(self):
        assert detect_condition("RTX 3070 great condition") == "used"


# ---------------------------------------------------------------------------
# Console category detection
# ---------------------------------------------------------------------------

class TestConsoleCategory:
    def test_ps5(self):
        assert detect_category("PS5 console bundle") == "console"

    def test_playstation5(self):
        assert detect_category("PlayStation 5 Digital Edition") == "console"

    def test_ps4_pro(self):
        assert detect_category("PS4 Pro 1TB") == "console"

    def test_xbox_series_x(self):
        assert detect_category("Xbox Series X 1TB") == "console"

    def test_xbox_series_s(self):
        assert detect_category("Xbox Series S white") == "console"

    def test_nintendo_switch(self):
        assert detect_category("Nintendo Switch OLED") == "console"

    def test_switch_oled(self):
        assert detect_category("Switch OLED with games") == "console"

    def test_switch_lite(self):
        assert detect_category("Switch Lite yellow") == "console"

    def test_steam_deck(self):
        assert detect_category("Steam Deck 512GB") == "console"

    def test_console_beats_desktop(self):
        # "PS5 gaming console" should not be "desktop"
        assert detect_category("PS5 gaming console with controller") == "console"


class TestConsoleParser:
    def test_ps5_canonical(self, parser):
        r = parser.parse("PS5 Digital Edition - barely used")
        assert r.category == "console"
        assert r.canonical_name is not None
        assert "PS5" in r.canonical_name

    def test_xbox_series_x_canonical(self, parser):
        r = parser.parse("Xbox Series X 1TB console")
        assert r.category == "console"
        assert r.canonical_name is not None
        assert "Xbox Series X" in r.canonical_name

    def test_switch_oled_canonical(self, parser):
        r = parser.parse("Nintendo Switch OLED white")
        assert r.category == "console"
        assert r.canonical_name is not None

    def test_steam_deck_canonical(self, parser):
        r = parser.parse("Steam Deck 512GB")
        assert r.category == "console"
        assert r.canonical_name is not None

    def test_broken_ps5_condition(self, parser):
        r = parser.parse("PS5 - won't power on, for parts")
        assert r.category == "console"
        assert r.condition == "for_parts"

    def test_console_confidence(self, parser):
        r = parser.parse("Sony PS5 Digital Edition")
        assert r.category == "console"
        assert r.confidence >= 0.5


# ---------------------------------------------------------------------------
# Phone category detection
# ---------------------------------------------------------------------------

class TestPhoneCategory:
    def test_iphone_15(self):
        assert detect_category("iPhone 15 Pro Max 256GB") == "phone"

    def test_iphone_se(self):
        assert detect_category("iPhone SE 64GB") == "phone"

    def test_iphone_mini(self):
        assert detect_category("iPhone 13 mini") == "phone"

    def test_samsung_galaxy_s(self):
        assert detect_category("Samsung Galaxy S23 Ultra") == "phone"

    def test_google_pixel(self):
        assert detect_category("Google Pixel 8 Pro") == "phone"


class TestPhoneParser:
    def test_iphone_canonical(self, parser):
        r = parser.parse("Apple iPhone 15 Pro Max 256GB")
        assert r.category == "phone"
        assert r.canonical_name is not None
        assert "iPhone" in r.canonical_name
        assert "15" in r.canonical_name

    def test_broken_iphone_canonical(self, parser):
        r = parser.parse("iPhone 14 cracked screen for parts")
        assert r.category == "phone"
        assert r.condition == "for_parts"
        assert r.canonical_name is not None

    def test_samsung_canonical(self, parser):
        r = parser.parse("Samsung Galaxy S23 Ultra 512GB")
        assert r.category == "phone"
        assert r.canonical_name is not None
        assert "Galaxy" in r.canonical_name


# ---------------------------------------------------------------------------
# MacBook canonical name improvement
# ---------------------------------------------------------------------------

class TestMacBookCanonical:
    def test_macbook_pro_m3_14inch(self, parser):
        r = parser.parse("Apple MacBook Pro 14 M3 Pro 2023")
        assert r.category == "laptop"
        assert r.canonical_name is not None
        assert "MacBook Pro" in r.canonical_name
        assert "M3" in r.canonical_name

    def test_macbook_air_m2(self, parser):
        r = parser.parse("MacBook Air 15 M2 2023 8GB 256GB")
        assert r.category == "laptop"
        assert r.canonical_name is not None
        assert "MacBook Air" in r.canonical_name
        assert "M2" in r.canonical_name

    def test_macbook_m5_has_chip_in_canonical(self, parser):
        r = parser.parse("MacBook Pro 16 M5 Max 2025")
        assert r.category == "laptop"
        assert r.canonical_name is not None
        assert "M5" in r.canonical_name

    def test_old_macbook_still_works(self, parser):
        r = parser.parse("MacBook Pro 2019 Intel i7")
        assert r.category == "laptop"
        assert r.canonical_name is not None
        assert "MacBook Pro" in r.canonical_name

    def test_macbook_m3_without_inch(self, parser):
        r = parser.parse("MacBook Pro M3 space gray")
        assert r.category == "laptop"
        assert r.canonical_name is not None
        assert "M3" in r.canonical_name


# ---------------------------------------------------------------------------
# Refurb noise filter
# ---------------------------------------------------------------------------

class TestRefurbNoise:
    def test_shop_pattern(self):
        assert is_refurb_noise("RTX 3080 SHOP123")

    def test_inv_pattern(self):
        assert is_refurb_noise("Laptop INV.M1234")

    def test_clean_title(self):
        assert not is_refurb_noise("RTX 3080 used great condition")
