from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .category_rules import (
    GPU_BRAND_PATTERNS, GPU_MODEL_PATTERNS,
    CPU_BRAND_PATTERNS, CPU_MODEL_PATTERNS,
    LAPTOP_BRAND_PATTERNS, LAPTOP_MODEL_PATTERNS,
    CONSOLE_BRAND_PATTERNS, CONSOLE_MODEL_PATTERNS,
    PHONE_BRAND_PATTERNS, PHONE_MODEL_PATTERNS,
    GPU_IN_SYSTEM_RE, CPU_IN_SYSTEM_RE,
    VRAM_PATTERN, RAM_CAPACITY_PATTERN,
    detect_category, detect_condition,
)


@dataclass
class ParsedTitle:
    category: Optional[str]
    brand: Optional[str]
    model: Optional[str]
    condition: str
    canonical_name: Optional[str]
    specs: Dict[str, Any]
    confidence: float


class TitleParser:
    """
    Extracts structured hardware identity from a raw listing title + description.

    Confidence scoring:
      - category identified: +0.3
      - brand identified:    +0.2
      - model identified:    +0.4
      - condition explicit:  +0.1
    Max = 1.0
    """

    def parse(self, title: str, description: str = "") -> ParsedTitle:
        text = f"{title} {description}"
        category = detect_category(text)
        condition = detect_condition(text)
        brand, model, specs = None, None, {}
        confidence = 0.0

        if category:
            confidence += 0.3
            if category == "gpu":
                brand = self._match_brand(text, GPU_BRAND_PATTERNS)
                model = self._match_model(text, GPU_MODEL_PATTERNS)
                vram_m = VRAM_PATTERN.search(text)
                if vram_m:
                    specs["vram_gb"] = int(vram_m.group(1))
            elif category == "cpu":
                brand = self._match_brand(text, CPU_BRAND_PATTERNS)
                model = self._match_model(text, CPU_MODEL_PATTERNS)
            elif category == "ram":
                cap_m = RAM_CAPACITY_PATTERN.search(text)
                if cap_m:
                    specs["capacity_gb"] = int(cap_m.group(1))
            elif category == "laptop":
                brand = self._match_brand(text, LAPTOP_BRAND_PATTERNS)
                model = self._match_model(text, LAPTOP_MODEL_PATTERNS)
                ram_m = RAM_CAPACITY_PATTERN.search(text)
                if ram_m:
                    specs["ram_gb"] = int(ram_m.group(1))
            elif category == "console":
                brand = self._match_brand(text, CONSOLE_BRAND_PATTERNS)
                model = self._match_model(text, CONSOLE_MODEL_PATTERNS)
            elif category == "phone":
                brand = self._match_brand(text, PHONE_BRAND_PATTERNS)
                model = self._match_model(text, PHONE_MODEL_PATTERNS)
                storage_m = re.search(r"(\d+)\s*GB\b", text, re.IGNORECASE)
                if storage_m:
                    specs["storage_gb"] = int(storage_m.group(1))
            elif category == "desktop":
                # For complete systems, extract the key component for the eBay search.
                # GPU is the primary differentiator for gaming PCs; fall back to CPU.
                gpu_m = GPU_IN_SYSTEM_RE.search(text)
                cpu_m = CPU_IN_SYSTEM_RE.search(text)
                if gpu_m:
                    model = self._clean(gpu_m.group(1))
                    # Brand is the system brand (Dell, HP, etc.) or None for custom builds.
                    brand = self._detect_oem_brand(text)
                elif cpu_m:
                    model = self._clean(cpu_m.group(1))
                    brand = self._detect_oem_brand(text)
                ram_m = RAM_CAPACITY_PATTERN.search(text)
                if ram_m:
                    specs["ram_gb"] = int(ram_m.group(1))

        if brand:
            confidence += 0.2
        if model:
            confidence += 0.4
        if condition != "used":
            confidence += 0.1

        canonical = self._build_canonical(category, brand, model, specs, text)

        return ParsedTitle(
            category=category,
            brand=brand,
            model=self._clean(model) if model else None,
            condition=condition,
            canonical_name=canonical,
            specs=specs,
            confidence=min(confidence, 1.0),
        )

    def _match_brand(self, text: str, patterns: list) -> Optional[str]:
        lower = text.lower()
        for pattern, brand in patterns:
            if re.search(pattern, lower):
                return brand
        return None

    def _match_model(self, text: str, patterns: list[str]) -> Optional[str]:
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _detect_oem_brand(self, text: str) -> Optional[str]:
        """Detect OEM brands (Dell, HP, etc.) in a desktop/system listing."""
        oem_patterns = [
            (r"\bdell\b", "Dell"),
            (r"\bhp\b|\bhewlett\b", "HP"),
            (r"\blenovo\b", "Lenovo"),
            (r"\basus\b", "ASUS"),
            (r"\bacer\b", "Acer"),
            (r"\bmsi\b", "MSI"),
            (r"\bcyberpowerpc\b|\bcyberpower\b", "CyberPowerPC"),
            (r"\bibrpowerpc\b|\bibuypower\b", "iBUYPOWER"),
            (r"\bnzxt\b", "NZXT"),
        ]
        lower = text.lower()
        for pattern, brand in oem_patterns:
            if re.search(pattern, lower):
                return brand
        return None

    def _clean(self, s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    def _build_canonical(
        self,
        category: Optional[str],
        brand: Optional[str],
        model: Optional[str],
        specs: Dict,
        text: str = "",
    ) -> Optional[str]:
        if not category:
            return None

        if category == "console":
            if not model:
                return None
            parts = []
            if brand:
                parts.append(brand)
            parts.append(self._clean(model))
            return " ".join(parts)

        if category == "phone":
            if not model:
                return None
            parts = []
            if brand:
                parts.append(brand)
            parts.append(self._clean(model))
            if "storage_gb" in specs:
                parts.append(f"{specs['storage_gb']}GB")
            return " ".join(parts)

        if category == "desktop":
            if not model:
                return None
            # Build an eBay-friendly system-level search query.
            # "Gaming PC RTX 3080" or "Dell Desktop i7-12700K"
            gpu_m = GPU_IN_SYSTEM_RE.search(text)
            if gpu_m:
                gpu = self._clean(gpu_m.group(1)).upper().replace("  ", " ")
                return f"Gaming PC {gpu}"
            cpu_m = CPU_IN_SYSTEM_RE.search(text)
            if cpu_m:
                cpu = self._clean(cpu_m.group(1))
                prefix = f"{brand} Desktop" if brand else "Desktop PC"
                return f"{prefix} {cpu}"
            return None

        if category == "laptop":
            if not model:
                # No specific model — too vague for reliable comps
                return None
            parts = []
            if brand:
                parts.append(brand)
            cleaned_model = self._clean(model)
            parts.append(cleaned_model)
            # For MacBooks without a chip variant in the captured model string,
            # append the year from the full text so Intel-era MacBooks don't share
            # comps with M-series (e.g. "Apple MacBook Pro 2017" vs "Apple MacBook Pro M3")
            if "MacBook" in cleaned_model and not re.search(r"\bM\d+\b", cleaned_model):
                year_m = re.search(r"\b(20(?:0[6-9]|1[0-9]|2[0-9]))\b", text)
                if year_m and year_m.group(1) not in cleaned_model:
                    parts.append(year_m.group(1))
            return " ".join(parts)

        # Components (gpu, cpu, ram, etc.)
        if not model:
            return None
        parts = []
        if brand:
            parts.append(brand)
        parts.append(self._clean(model))
        if category == "gpu" and "vram_gb" in specs:
            parts.append(f"{specs['vram_gb']}GB")
        return " ".join(parts)
