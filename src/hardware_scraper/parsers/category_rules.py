from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Category keyword rules
# ---------------------------------------------------------------------------

# System-level categories (desktop, laptop) are checked FIRST before components.
# This ensures "Gaming PC with RTX 2060" → desktop, not gpu.
_SYSTEM_CATEGORY_PATTERNS: list[tuple[str, list[str]]] = [
    ("desktop", [
        r"\bdesktop\b", r"\bprebuilt\b", r"\bgaming\s+pc\b", r"\bcomplete\s+build\b",
        r"\bgaming\s+computer\b", r"\bcustom\s+build\b", r"\bfull\s+build\b",
        r"\btower\s+pc\b", r"\bpc\s+build\b", r"\bcomplete\s+system\b",
        r"\bworkstation\b", r"\bcomplete\s+setup\b",
    ]),
    ("laptop", [
        r"\blaptop\b", r"\bnotebook\b", r"\bthinkpad\b", r"\bmacbook\b",
        r"\bchromebook\b", r"\bultrabook\b", r"\bzenbook\b", r"\bvivobook\b",
        r"\belitebook\b", r"\bprobook\b", r"\blatitude\s+\d", r"\binspirion\b",
        r"\bxps\s+\d", r"\bsurface\s+(?:pro|laptop|book)\b",
    ]),
]

_COMPONENT_CATEGORY_PATTERNS: list[tuple[str, list[str]]] = [
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
]

_CONDITION_PATTERNS: list[tuple[str, list[str]]] = [
    ("for_parts", [r"\bfor\s+parts?\b", r"\bnot\s+working\b", r"\bbroken\b", r"\bdead\b",
                   r"\buntested\b", r"\bas[- ]is\b"]),
    ("like_new", [r"\blike\s+new\b", r"\bopen\s+box\b", r"\bsealed\b", r"\bnib\b",
                  r"\bnever\s+used\b", r"\bmint\b"]),
    ("used", []),  # default / fallback
]

# ---------------------------------------------------------------------------
# Refurb / reseller noise patterns
# ---------------------------------------------------------------------------

_REFURB_NOISE_PATTERNS = [
    r"\bSHOP\s*\d+\b",        # "SHOP12", "SHOP 34"
    r"\bINV\.?\s*[A-Z]?\d{3,}\b",  # "INV.M1234", "INV 567"
    r"\bINV-\d+\b",            # "INV-1234"
]


def is_refurb_noise(title: str) -> bool:
    """Return True if the listing title looks like a local refurb reseller's inventory tag."""
    for pattern in _REFURB_NOISE_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False


# ---------------------------------------------------------------------------
# Brand / model regexes — components
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

# ---------------------------------------------------------------------------
# Brand / model regexes — laptops
# ---------------------------------------------------------------------------

LAPTOP_BRAND_PATTERNS = [
    (r"\blenovo\b|\bthinkpad\b|\bideapad\b", "Lenovo"),
    (r"\bdell\b|\blatitude\b|\binspirion\b|\bxps\b", "Dell"),
    (r"\bhp\b|\belitebook\b|\bprobook\b|\bpavilion\b|\benvy\b|\bomen\b", "HP"),
    (r"\basus\b|\bzenbook\b|\bvivobook\b|\brog\b", "ASUS"),
    (r"\bacer\b|\baspire\b|\bnitro\b|\bswift\b", "Acer"),
    (r"\bmicrosoft\b|\bsurface\b", "Microsoft"),
    (r"\bapple\b|\bmacbook\b", "Apple"),
    (r"\bsamsung\b|\bgalaxy\s+book", "Samsung"),
    (r"\bmsi\b", "MSI"),
    (r"\brazer\b|\bblade\b", "Razer"),
]

# Ordered most-specific first so ThinkPad X1 Carbon beats ThinkPad X1
LAPTOP_MODEL_PATTERNS = [
    r"(ThinkPad\s+X1\s+(?:Carbon|Yoga|Extreme|Nano)(?:\s+Gen\s*\d+)?)",
    r"(ThinkPad\s+[A-Z]\d+[a-z]?(?:\s+Gen\s*\d+)?)",
    r"(MacBook\s+(?:Pro|Air)(?:\s+M\d)?(?:\s+\d{4})?)",
    r"(EliteBook\s+\d+\w*\s*G\d+)",
    r"(ProBook\s+\d+\w*\s*G\d*)",
    r"(Latitude\s+[A-Z]?\d+\w*)",
    r"(Inspiron\s+\d+\w*)",
    r"(XPS\s+\d+\w*)",
    r"(ZenBook\s+\w+(?:\s+\w+)?)",
    r"(VivoBook\s+\w+(?:\s+\w+)?)",
    r"(ROG\s+(?:Zephyrus|Strix|Flow)\s+\w+)",
    r"(Surface\s+(?:Pro|Laptop|Book)\s*\d*)",
    r"(IdeaPad\s+\w+(?:\s+\w+)?)",
    r"(Aspire\s+\w+(?:\s+\w+)?)",
    r"(Nitro\s+\d+\w*)",
    r"(Razer\s+Blade\s+\w*)",
]

# Used inside desktop canonical name building
GPU_IN_SYSTEM_RE = re.compile(
    r"(RTX\s*\d{4}\s*(?:Ti|Super)?|GTX\s*\d{4}\s*(?:Ti|Super)?|RX\s*\d{4}\s*(?:XT|XTX)?)",
    re.IGNORECASE,
)
CPU_IN_SYSTEM_RE = re.compile(
    r"(i[3579][- ]\d{4,5}[A-Z]*|Ryzen\s+[3579]\s+\d{4}[A-Z]*)",
    re.IGNORECASE,
)

VRAM_PATTERN = re.compile(r"(\d+)\s*GB?\s*(?:VRAM|GDDR)", re.IGNORECASE)
RAM_CAPACITY_PATTERN = re.compile(r"(\d+)\s*GB?\s*(?:DDR[45]?|RAM|Memory)", re.IGNORECASE)


def detect_category(text: str) -> Optional[str]:
    lower = text.lower()
    # System-level categories win over components — check them first.
    for category, patterns in _SYSTEM_CATEGORY_PATTERNS:
        if any(re.search(p, lower) for p in patterns):
            return category
    for category, patterns in _COMPONENT_CATEGORY_PATTERNS:
        if any(re.search(p, lower) for p in patterns):
            return category
    return None


def detect_condition(text: str) -> str:
    lower = text.lower()
    for condition, patterns in _CONDITION_PATTERNS:
        if patterns and any(re.search(p, lower) for p in patterns):
            return condition
    return "used"
