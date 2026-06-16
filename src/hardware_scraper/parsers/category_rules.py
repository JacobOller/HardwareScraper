from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Category keyword rules
# ---------------------------------------------------------------------------

_CATEGORY_PATTERNS: list[tuple[str, list[str]]] = [
    ("gpu", [r"\brtx\s*\d{4}", r"\bgtx\s*\d{4}", r"\brx\s*\d{4}", r"\bradeon\s*r[xyz]\s*\d{4}",
             r"\bgraphics\s+card", r"\bvideo\s+card", r"\bgpu\b"]),
    ("cpu", [r"\bcore\s+i[3579][- ]\d{4,5}", r"\bryzen\s+[3579]\s+\d{4}", r"\bxeon\b",
             r"\bprocessor\b", r"\bcpu\b", r"\bthreadripper\b"]),
    ("ram", [r"\bddr[45]\b", r"\bram\b", r"\bmemory\b", r"\bdimm\b", r"\bso-?dimm\b"]),
    ("ssd", [r"\bnvme\b", r"\bssd\b", r"\bm\.?2\b", r"\bsolid\s+state"]),
    ("hdd", [r"\bhdd\b", r"\bhard\s+drive\b", r"\bhard\s+disk\b"]),
    ("motherboard", [r"\bmotherboard\b", r"\bmobo\b", r"\bam[45]\b", r"\blga\s*\d{4}"]),
    ("psu", [r"\bpsu\b", r"\bpower\s+supply\b", r"\bwatt\b", r"\b\d{3,4}w\b"]),
    ("cooling", [r"\bcpu\s+cooler\b", r"\bnoctua\b", r"\bair\s+cooler\b", r"\baio\b",
                 r"\bliquid\s+cooler\b", r"\bradiat"]),
    ("case", [r"\bpc\s+case\b", r"\bmid\s+tower\b", r"\bfull\s+tower\b", r"\batx\s+case\b"]),
    ("laptop", [r"\blaptop\b", r"\bnotebook\b", r"\bthinkpad\b", r"\bmacbook\b"]),
    ("desktop", [r"\bdesktop\b", r"\bprebuilt\b", r"\bgaming\s+pc\b", r"\bcomplete\s+build\b"]),
]

_CONDITION_PATTERNS: list[tuple[str, list[str]]] = [
    ("for_parts", [r"\bfor\s+parts?\b", r"\bnot\s+working\b", r"\bbroken\b", r"\bdead\b",
                   r"\buntested\b", r"\bas[- ]is\b"]),
    ("like_new", [r"\blike\s+new\b", r"\bopen\s+box\b", r"\bsealed\b", r"\bnib\b",
                  r"\bnever\s+used\b", r"\bmint\b"]),
    ("used", []),  # default / fallback
]

# ---------------------------------------------------------------------------
# Brand / model regexes
# ---------------------------------------------------------------------------

GPU_BRAND_PATTERNS = [
    (r"\bnvidia\b", "NVIDIA"),
    (r"\bamd\b|\bradeon\b|\brx\s*\d{4}", "AMD"),
    (r"\bintel\s+arc\b|\barc\s+a\d{3}", "Intel"),
]

GPU_MODEL_PATTERNS = [
    r"(RTX\s*\d{4}\s*(?:Ti|Super)?)",
    r"(GTX\s*\d{4}\s*(?:Ti|Super)?)",
    r"(RX\s*\d{4}\s*(?:XT|XTX)?)",
    r"(Arc\s*A\d{3}(?:\s*\w+)?)",
]

CPU_BRAND_PATTERNS = [
    (r"\bintel\b|\bcore\s+i[3579]\b|\bxeon\b", "Intel"),
    (r"\bamd\b|\bryzen\b|\bthreadripper\b|\bepyc\b", "AMD"),
]

CPU_MODEL_PATTERNS = [
    r"(i[3579][- ]\d{4,5}[A-Z]*)",
    r"(Ryzen\s+[3579]\s+\d{4}[A-Z]*)",
    r"(Xeon\s+\w+[- ]\d+\w*)",
    r"(Threadripper\s+\w+)",
]

VRAM_PATTERN = re.compile(r"(\d+)\s*GB?\s*(?:VRAM|GDDR)", re.IGNORECASE)
RAM_CAPACITY_PATTERN = re.compile(r"(\d+)\s*GB?\s*(?:DDR[45]?|RAM|Memory)", re.IGNORECASE)


def detect_category(text: str) -> Optional[str]:
    lower = text.lower()
    for category, patterns in _CATEGORY_PATTERNS:
        if any(re.search(p, lower) for p in patterns):
            return category
    return None


def detect_condition(text: str) -> str:
    lower = text.lower()
    for condition, patterns in _CONDITION_PATTERNS:
        if patterns and any(re.search(p, lower) for p in patterns):
            return condition
    return "used"
