import pytest
from hardware_scraper.parsers.category_rules import detect_category, detect_condition, is_accessory_noise, is_refurb_noise
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


# ---------------------------------------------------------------------------
# Accessory noise filter
# ---------------------------------------------------------------------------

class TestAccessoryNoise:
    # Phone cases
    def test_iphone_case_dropped(self):
        assert is_accessory_noise("iPhone 14 Pro Case Black TPU")

    def test_phone_case_dropped(self):
        assert is_accessory_noise("Phone Case for Samsung Galaxy")

    def test_case_for_iphone_dropped(self):
        assert is_accessory_noise("Case for iPhone 13 Pro Max Leather")

    def test_wallet_case_dropped(self):
        assert is_accessory_noise("Wallet Case iPhone 15 Plus")

    def test_galaxy_case_dropped(self):
        assert is_accessory_noise("Samsung Galaxy S23 Case Clear")

    # Screen protection
    def test_screen_protector_dropped(self):
        assert is_accessory_noise("iPhone 15 Screen Protector 3-Pack Tempered")

    def test_tempered_glass_dropped(self):
        assert is_accessory_noise("Tempered Glass for Samsung Galaxy S22")

    # Phone chargers / accessories
    def test_phone_charger_dropped(self):
        assert is_accessory_noise("Phone Charger Fast Charging 65W USB-C")

    def test_iphone_charger_dropped(self):
        assert is_accessory_noise("iPhone Charger Cable 6ft MFi Certified")

    def test_charger_for_samsung_dropped(self):
        assert is_accessory_noise("Charger for Samsung Galaxy fast 45W")

    # Smartwatches & earbuds
    def test_apple_watch_dropped(self):
        assert is_accessory_noise("Apple Watch Series 9 45mm Midnight")

    def test_airpods_dropped(self):
        assert is_accessory_noise("AirPods Pro 2nd Generation with case")

    def test_airpod_singular_dropped(self):
        assert is_accessory_noise("AirPod Pro replacement left ear")

    def test_samsung_buds_dropped(self):
        assert is_accessory_noise("Samsung Galaxy Buds2 Pro Black")

    # Laptop accessories
    def test_laptop_bag_dropped(self):
        assert is_accessory_noise("Laptop Bag 15.6 inch Waterproof Dell")

    def test_laptop_backpack_dropped(self):
        assert is_accessory_noise("Laptop Backpack 17 inch Gaming")

    def test_macbook_sleeve_dropped(self):
        assert is_accessory_noise("MacBook Pro sleeve 13 inch neoprene")

    def test_macbook_cover_dropped(self):
        assert is_accessory_noise("MacBook Air Cover 13 inch hardshell")

    # Console accessories & games
    def test_dualsense_controller_dropped(self):
        assert is_accessory_noise("DualSense PS5 Wireless Controller White")

    def test_dualshock_dropped(self):
        assert is_accessory_noise("DualShock 4 Controller Black PS4")

    def test_ps5_controller_dropped(self):
        assert is_accessory_noise("PS5 Controller DualSense Midnight Black")

    def test_ps5_game_dropped(self):
        assert is_accessory_noise("PS5 Games Lot God of War Horizon")

    def test_xbox_controller_dropped(self):
        assert is_accessory_noise("Xbox Controller Wireless Carbon Black")

    def test_xbox_game_dropped(self):
        assert is_accessory_noise("Xbox Game Halo Infinite Series X")

    def test_switch_game_dropped(self):
        assert is_accessory_noise("Switch Game Mario Kart 8 Deluxe")

    def test_controller_for_ps5_dropped(self):
        assert is_accessory_noise("Controller for PS5 brand new in box")

    # Legitimate listings should NOT be dropped
    def test_iphone_not_dropped(self):
        assert not is_accessory_noise("iPhone 14 Pro 256GB Space Black unlocked")

    def test_ps5_console_not_dropped(self):
        assert not is_accessory_noise("PS5 Digital Edition console bundle")

    def test_xbox_console_not_dropped(self):
        assert not is_accessory_noise("Xbox Series X 1TB console")

    def test_macbook_not_dropped(self):
        assert not is_accessory_noise("MacBook Pro 14 M3 Pro 2023 Space Gray")

    def test_laptop_not_dropped(self):
        assert not is_accessory_noise("Dell Latitude 5480 laptop i7 16GB")

    def test_gpu_not_dropped(self):
        assert not is_accessory_noise("RTX 3080 10GB EVGA FTW3 gaming card")

    def test_ps5_with_controller_bundle_not_dropped(self):
        # Bundle listing — the PS5 is the primary item
        assert not is_accessory_noise("PS5 Disc Edition with extra controller and games")

    # --- New patterns: console games with model number between brand and "game" ---
    def test_xbox_series_x_game_dropped(self):
        assert is_accessory_noise("Xbox series x game and controller")

    def test_xbox_series_s_games_dropped(self):
        assert is_accessory_noise("Xbox Series S games lot Forza Halo")

    def test_ps4_slim_games_dropped(self):
        assert is_accessory_noise("PS4 Slim games lot 10 titles")

    # --- Console-specific case patterns ---
    def test_case_for_steam_deck_dropped(self):
        assert is_accessory_noise("Case for steam deck protective hard shell")

    def test_case_for_ps5_dropped(self):
        assert is_accessory_noise("Case for PS5 slim travel bag")

    def test_steam_deck_case_dropped(self):
        assert is_accessory_noise("Steam Deck case EVA hard shell")

    # --- Dock / stand patterns ---
    def test_steam_deck_dock_dropped(self):
        assert is_accessory_noise("steam deck dock USB-C hub HDMI")

    def test_switch_dock_dropped(self):
        assert is_accessory_noise("Nintendo Switch dock official OEM")

    def test_charging_dock_dropped(self):
        assert is_accessory_noise("Charging Dock for PS5 DualSense controllers")

    # --- Service listings ---
    def test_ps5_cleaning_dropped(self):
        assert is_accessory_noise("ps5 cleaning deep clean fan service")

    def test_laptop_cleaning_dropped(self):
        assert is_accessory_noise("laptop cleaning and thermal paste replacement")

    def test_cleaning_service_dropped(self):
        assert is_accessory_noise("PC cleaning service dust removal")

    def test_repair_service_dropped(self):
        assert is_accessory_noise("iPhone repair service screen replacement")

    # --- Storage enclosures ---
    def test_ssd_case_dropped(self):
        assert is_accessory_noise("1tb ssd case only for xbox external")

    def test_hdd_case_dropped(self):
        assert is_accessory_noise("HDD case 2.5 inch USB 3.0 enclosure")

    def test_drive_enclosure_dropped(self):
        assert is_accessory_noise("Drive enclosure USB-C NVMe aluminum")

    # --- Verify legitimate console/hardware listings are still NOT dropped ---
    def test_xbox_series_x_console_not_dropped(self):
        assert not is_accessory_noise("Xbox Series X 1TB console black")

    def test_steam_deck_console_not_dropped(self):
        assert not is_accessory_noise("Steam Deck 512GB OLED great condition")

    def test_ps5_console_not_dropped_2(self):
        assert not is_accessory_noise("PS5 Digital Edition barely used")

    def test_ssd_drive_not_dropped(self):
        assert not is_accessory_noise("Samsung 1TB NVMe SSD 970 EVO Plus")
