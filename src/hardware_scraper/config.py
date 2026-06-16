from __future__ import annotations

from pathlib import Path
from typing import List

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def _load_yaml() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
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
    ebay_rate: float = 0.1325
    ebay_fixed: float = 0.30
    outbound_shipping: float = 15.00


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


_instance: AppConfig | None = None


def get_config() -> AppConfig:
    global _instance
    if _instance is None:
        _instance = AppConfig()
    return _instance
