from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"
_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(obj):
    """Recursively replace ${VAR_NAME} in string values with the env var value."""
    if isinstance(obj, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), obj)
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


def _load_yaml() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}
        return _expand_env_vars(raw)
    return {}


class EbayConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    app_id: str = ""
    cert_id: str = ""
    environment: str = "production"
    comps_days_back: int = 60
    comps_cache_hours: int = 24
    max_comps_per_query: int = 50


class FeesConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    amazon_referral_rate: float = 0.08
    amazon_per_item_fee: float = 0.99
    outbound_shipping: float = 15.00


class ShippingConfig:
    """Per-category outbound shipping estimates."""

    def __init__(self, default: float = 15.00, by_category: Optional[Dict] = None) -> None:
        self.default = default
        self.by_category: Dict[str, float] = {
            k: float(v) for k, v in (by_category or {}).items()
        }

    def for_category(self, category: Optional[str]) -> float:
        if category and category in self.by_category:
            return self.by_category[category]
        return self.default


class MarginTiers(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    excellent: int = 50
    good: int = 30
    marginal: int = 15
    low: int = 0


class ScrapingConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    location_zip: str = ""
    radius_miles: int = 25
    rate_limit_seconds: float = 3.0
    headless: bool = True
    session_dir: str = "data/browser_session"


class SearchConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    queries: List[str] = []


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    url: str = "sqlite:///data/hardware_scraper.db"


class OutputConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    csv_dir: str = "data/exports"
    min_margin_to_show: int = 0


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    enabled: bool = False
    api_key: str = ""
    model: str = "claude-haiku-4-5"
    confidence_threshold: float = 0.5
    validate_margin_threshold: float = 60.0


class FacebookConfig:
    def __init__(
        self,
        session_dir: str = "data/facebook_session",
        enabled: bool = True,
        headless: bool = True,
        latitude: float = 0.0,
        longitude: float = 0.0,
        radius_miles: int = 40,
        city_marketplace_url: str = "",
    ) -> None:
        self.session_dir = session_dir
        self.enabled = enabled
        self.headless = headless
        self.latitude = latitude
        self.longitude = longitude
        self.radius_miles = radius_miles
        self.city_marketplace_url = city_marketplace_url


class CraigslistConfig:
    def __init__(self, enabled: bool = True, subdomain: str = "boston") -> None:
        self.enabled = enabled
        self.subdomain = subdomain


class MercariConfig:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled


class EbayLocalConfig:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled


class AppConfig:
    def __init__(self) -> None:
        raw = _load_yaml()
        self.ebay = EbayConfig(**raw.get("ebay", {}))
        self.fees = FeesConfig(**raw.get("fees", {}))
        self.margin_tiers = MarginTiers(**raw.get("margin_tiers", {}))
        self.scraping = ScrapingConfig(**raw.get("scraping", {}))
        self.search = SearchConfig(**raw.get("search", {}))
        self.database = DatabaseConfig(**raw.get("database", {}))
        self.output = OutputConfig(**raw.get("output", {}))
        self.llm = LLMConfig(**raw.get("llm", {}))

        ship_raw = raw.get("shipping", {})
        self.shipping = ShippingConfig(
            default=float(ship_raw.get("default", self.fees.outbound_shipping)),
            by_category=ship_raw.get("by_category", {}),
        )

        fb_raw = raw.get("facebook", {})
        self.facebook = FacebookConfig(
            session_dir=fb_raw.get("session_dir", "data/facebook_session"),
            enabled=bool(fb_raw.get("enabled", True)),
            headless=bool(fb_raw.get("headless", True)),
            latitude=float(fb_raw.get("latitude", 0.0)),
            longitude=float(fb_raw.get("longitude", 0.0)),
            radius_miles=int(fb_raw.get("radius_miles", self.scraping.radius_miles)),
            city_marketplace_url=str(fb_raw.get("city_marketplace_url", "")),
        )

        cl_raw = raw.get("craigslist", {})
        self.craigslist = CraigslistConfig(
            enabled=bool(cl_raw.get("enabled", True)),
            subdomain=str(cl_raw.get("subdomain", "boston")),
        )

        self.mercari = MercariConfig(
            enabled=bool(raw.get("mercari", {}).get("enabled", True))
        )

        self.ebay_local = EbayLocalConfig(
            enabled=bool(raw.get("ebay_local", {}).get("enabled", True))
        )


_instance: AppConfig | None = None


def get_config() -> AppConfig:
    global _instance
    if _instance is None:
        _instance = AppConfig()
    return _instance
