from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Category keyword rules
# ---------------------------------------------------------------------------

# System-level categories checked FIRST. Order matters:
#   console > phone > desktop > laptop > components
# "Gaming PC with RTX 2060" → desktop, not gpu.
# "PS5 console" → console, not desktop.
_SYSTEM_CATEGORY_PATTERNS: list[tuple[str, list[str]]] = [
    ("console", [
        r"\bps5\b", r"\bplaystation\s*5\b", r"\bps4\s*(?:pro|slim)?\b", r"\bplaystation\s*4\b",
        r"\bxbox\s+series\s+[xs]\b", r"\bxbox\s+one\s*[xs]?\b",
        r"\bnintendo\s+switch\b", r"\bswitch\s+oled\b", r"\bswitch\s+lite\b",
        r"\bsteam\s+deck\b",
    ]),
    ("phone", [
        r"\biphone\s*(?:se|mini|\d+)\b", r"\biphone\s+pro\b", r"\biphone\s+max\b",
        r"\bsamsung\s+galaxy\s+[as]\d+", r"\bgoogle\s+pixel\s+\d+",
    ]),
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
    ("for_parts", [
        r"\bfor\s+parts?\b", r"\bnot\s+working\b", r"\bbroken\b", r"\bdead\b",
        r"\buntested\b", r"\bas[- ]is\b", r"\bno\s+display\b", r"\bno\s+post\b",
        r"\bno\s+power\b", r"\bwon['’]?t\s+power\s+on\b", r"\bpowers?\s+on\s+but\b",
        r"\bcracked\s+screen\b", r"\bshattered\s+screen\b", r"\bbad\s+battery\b",
        r"\bbent\s+pins?\b", r"\bwater\s+damage[d]?\b", r"\bwater\s+damaged?\b",
        r"\bbad\s+gpu\b", r"\bbios\s+only\b", r"\bsold\s+as\s+is\b",
        r"\bdoes\s+not\s+turn\s+on\b", r"\bwont\s+turn\s+on\b", r"\bno\s+boot\b",
        r"\bdamaged\b",
    ]),
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
# Accessory noise patterns — drop before category detection
# Catches accessories misidentified as the parent product
# (e.g. "iPhone 14 Case" → phone category with $800 eBay comp)
# ---------------------------------------------------------------------------

_ACCESSORY_NOISE_PATTERNS = [
    # Phone cases & covers — allow model info between brand and "case"
    r"\bphone\s+case\b",
    r"\bphone\s+cover\b",
    r"\biphone\b.{0,25}\bcase\b",   # "iPhone 14 Pro Case"
    r"\bcase\s+for\s+(?:iphone|samsung|galaxy|pixel|android|phone)\b",
    r"\bsamsung\b.{0,25}\bcase\b",  # "Samsung Galaxy S23 Case"
    r"\bgalaxy\b.{0,25}\bcase\b",   # "Galaxy S23 Ultra Case"
    r"\bwallet\s+case\b",
    r"\bfolio\s+case\b",
    # Screen protection
    r"\bscreen\s+protector\b",
    r"\btempered\s+glass\b",
    # Phone chargers / accessories
    r"\bphone\s+(?:charger|stand|mount|holder)\b",
    r"\bcharger\s+for\s+(?:iphone|samsung|galaxy|pixel|phone|android)\b",
    r"\biphone\s+charger\b",
    # Smartwatches & wireless earbuds (often trigger phone category)
    r"\bapple\s+watch\b",
    r"\bairpods?\b",
    r"\bsamsung\s+(?:galaxy\s+)?buds\d*\b",  # "Galaxy Buds2 Pro"
    r"\bpixel\s+buds\b",
    # Laptop bags / sleeves — allow "Pro/Air" between MacBook and accessory type
    r"\blaptop\s+(?:bag|backpack|sleeve|case|cover)\b",
    r"\bmacbook\b.{0,10}\b(?:case|cover|skin|sleeve|bag)\b",  # "MacBook Pro sleeve"
    # Console controllers & games (not the console itself)
    r"\bdualsense\b",
    r"\bdualshock\b",
    r"\bps[45]\s+controller\b",
    r"\bps5\s+game[s]?\b",
    r"\bxbox\s+(?:game[s]?|controller)\b",
    r"\bxbox\b.{0,25}\bgame[s]?\b",  # "Xbox Series X game" (model between brand and "game")
    r"\bps[45]\b.{0,20}\bgame[s]?\b",  # "PS4 Slim games lot"
    r"\bswitch\s+game[s]?\b",
    r"\bnintendo\s+(?:game[s]?|cartridge)\b",
    r"\bcontroller\s+for\s+(?:ps[45]|xbox|switch|playstation|nintendo)\b",
    # Console cases, docks, and stands
    r"\bcase\s+for\s+(?:steam\s+deck|ps[45]|xbox|switch|playstation|nintendo|console)\b",
    r"\bsteam\s+deck\s+(?:dock|stand|charger|hub|case|cover|skin|bag)\b",
    r"\bswitch\s+(?:dock|hub|stand)\b",
    r"\bcharging\s+(?:dock|station)\b",
    # Service / cleaning listings
    r"\b(?:ps[45]|xbox|switch|console|laptop|pc)\s+cleaning\b",
    r"\bcleaning\s+service\b",
    r"\brepair\s+service\b",
    # External drive enclosures (trigger ssd/hdd category but aren't drives)
    r"\bssd\s+case\b",
    r"\bhdd\s+case\b",
    r"\bdrive\s+enclosure\b",
]


def is_accessory_noise(title: str) -> bool:
    """Return True if the title is an accessory being misidentified as the parent product."""
    for pattern in _ACCESSORY_NOISE_PATTERNS:
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
    # MacBook: capture screen size (14/16/13 inch), chip (M1/M2/M3/M4/M5 + Pro/Max/Ultra), year
    r"(MacBook\s+(?:Pro|Air)(?:\s+\d{2}(?:[- ]?inch)?)?(?:\s+M\d+(?:\s+(?:Pro|Max|Ultra))?)?(?:\s+\d{4})?)",
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

# ---------------------------------------------------------------------------
# Brand / model regexes — consoles
# ---------------------------------------------------------------------------

CONSOLE_BRAND_PATTERNS = [
    (r"\bsony\b|\bplaystation\b|\bps[45]\b", "Sony"),
    (r"\bmicrosoft\b|\bxbox\b", "Microsoft"),
    (r"\bnintendo\b|\bswitch\b", "Nintendo"),
    (r"\bvalve\b|\bsteam\s+deck\b", "Valve"),
]

CONSOLE_MODEL_PATTERNS = [
    r"(PS5\s*(?:Digital\s+Edition|Disc\s+Edition)?)",
    r"(PlayStation\s*5\s*(?:Digital\s+Edition|Disc\s+Edition)?)",
    r"(Xbox\s+Series\s+[XS])",
    r"(Nintendo\s+Switch\s*(?:OLED|Lite|V2)?)",
    r"(Switch\s*(?:OLED|Lite|V2)?)",
    r"(Steam\s+Deck\s*(?:\d+\s*GB)?)",
    r"(PS4\s*(?:Pro|Slim)?)",
    r"(PlayStation\s*4\s*(?:Pro|Slim)?)",
    r"(Xbox\s+One\s*[XS]?)",
]

# ---------------------------------------------------------------------------
# Brand / model regexes — phones
# ---------------------------------------------------------------------------

PHONE_BRAND_PATTERNS = [
    (r"\bapple\b|\biphone\b", "Apple"),
    (r"\bsamsung\b|\bgalaxy\b", "Samsung"),
    (r"\bgoogle\b|\bpixel\b", "Google"),
]

PHONE_MODEL_PATTERNS = [
    r"(iPhone\s+(?:SE|mini|\d+)\s*(?:Pro\s+Max|Pro|Plus|Max)?)",
    r"(Galaxy\s+[AS]\d+\s*(?:Ultra|Plus|\+)?)",
    r"(Pixel\s+\d+\s*(?:Pro|XL|a)?)",
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
