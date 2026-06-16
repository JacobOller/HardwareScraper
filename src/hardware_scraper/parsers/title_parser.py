from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .category_rules import (
    GPU_BRAND_PATTERNS, GPU_MODEL_PATTERNS,
    CPU_BRAND_PATTERNS, CPU_MODEL_PATTERNS,
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

        if brand:
            confidence += 0.2
        if model:
            confidence += 0.4
        if condition != "used":
            confidence += 0.1

        canonical = self._build_canonical(category, brand, model, specs)

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

    def _clean(self, s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    def _build_canonical(
        self,
        category: Optional[str],
        brand: Optional[str],
        model: Optional[str],
        specs: Dict,
    ) -> Optional[str]:
        if not (category and model):
            return None
        parts = []
        if brand:
            parts.append(brand)
        parts.append(self._clean(model))
        if category == "gpu" and "vram_gb" in specs:
            parts.append(f"{specs['vram_gb']}GB")
        return " ".join(parts)
