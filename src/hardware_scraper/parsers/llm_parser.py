from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .title_parser import ParsedTitle


class LLMParser:
    """
    Sends low-confidence listing titles to Claude Haiku for structured extraction.
    Returns the same ParsedTitle format as TitleParser.
    Also provides check_condition() for titles that defer to the description.
    """

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5") -> None:
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def check_condition(self, title: str, description: str, category: str) -> Optional[str]:
        """
        Determine condition for listings with vague titles like 'see description'.
        Returns 'for_parts', 'like_new', or 'used'; None if cannot determine.
        """
        prompt = f"""A local marketplace listing for a {category} has a vague title. Determine its condition from the description.

Title: {title}
Description: {description[:800] or "(none)"}

Condition options:
- for_parts: broken, not working, damaged, cracked screen, water damage, missing components, powers on but has issues, needs repair
- like_new: barely used, mint, open box, never used, factory sealed
- used: works normally, general wear and tear

Reply with only one word: used, like_new, or for_parts"""
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=16,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.content[0].text.strip().lower()
            if "for_parts" in answer or "parts" in answer:
                return "for_parts"
            if "like_new" in answer or "like new" in answer:
                return "like_new"
            if "used" in answer:
                return "used"
        except Exception:
            pass
        return None

    def parse(self, title: str, description: str = "") -> ParsedTitle:
        prompt = _build_prompt(title, description)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_response(response.content[0].text)


def _build_prompt(title: str, description: str) -> str:
    return f"""Extract hardware details from this marketplace listing. Return ONLY valid JSON, no markdown.

Title: {title}
Description: {description or "(none)"}

Return a JSON object with these fields (use null if unknown):
{{
  "category": one of ["gpu","cpu","ram","ssd","hdd","motherboard","psu","cooling","case","laptop","desktop","console","phone"] or null,
  "brand": manufacturer name string or null,
  "model": specific model string (e.g. "RTX 3080", "i7-12700K", "PS5 Digital Edition", "iPhone 15 Pro") or null,
  "condition": one of ["used","like_new","for_parts"] — use "for_parts" for broken/damaged/not working/no display/cracked screen/water damage items,
  "specs": object with known specs (e.g. {{"vram_gb": 10}} for GPUs, {{"capacity_gb": 32}} for RAM, {{"storage_gb": 256}} for phones) or {{}}
}}"""


def _parse_response(text: str) -> ParsedTitle:
    try:
        text = text.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else parts[0]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
        if isinstance(data, list):
            data = data[0] if data else {}
    except (json.JSONDecodeError, IndexError):
        return _empty_parsed()

    if not isinstance(data, dict):
        return _empty_parsed()

    category: Optional[str] = data.get("category")
    brand: Optional[str] = data.get("brand")
    model: Optional[str] = data.get("model")
    condition: str = data.get("condition") or "used"
    specs: Dict[str, Any] = data.get("specs") or {}

    canonical = _build_canonical(category, brand, model, specs)
    confidence = _score_confidence(category, brand, model, condition)

    return ParsedTitle(
        category=category,
        brand=brand,
        model=model,
        condition=condition,
        canonical_name=canonical,
        specs=specs,
        confidence=confidence,
    )


def _build_canonical(
    category: Optional[str],
    brand: Optional[str],
    model: Optional[str],
    specs: Dict[str, Any],
) -> Optional[str]:
    if not (category and model):
        return None
    parts = []
    if brand:
        parts.append(brand)
    parts.append(model)
    if category == "gpu" and "vram_gb" in specs:
        parts.append(f"{specs['vram_gb']}GB")
    return " ".join(parts)


def _score_confidence(
    category: Optional[str],
    brand: Optional[str],
    model: Optional[str],
    condition: str,
) -> float:
    score = 0.0
    if category:
        score += 0.3
    if brand:
        score += 0.2
    if model:
        score += 0.4
    if condition != "used":
        score += 0.1
    return min(score, 1.0)


def _empty_parsed() -> ParsedTitle:
    return ParsedTitle(
        category=None,
        brand=None,
        model=None,
        condition="used",
        canonical_name=None,
        specs={},
        confidence=0.0,
    )
