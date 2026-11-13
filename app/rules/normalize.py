"""Small, exact helpers shared by the rules, tools and data generator."""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def gstin_check_char(first14: str) -> str:
    """Luhn mod-36 check character used by GSTIN."""
    factor, total, mod = 2, 0, 36
    for ch in reversed(first14):
        digit = factor * GSTIN_CHARS.index(ch)
        factor = 1 if factor == 2 else 2
        total += digit // mod + digit % mod
    return GSTIN_CHARS[(mod - total % mod) % mod]


def gstin_is_valid(gstin: str) -> bool:
    g = (gstin or "").strip().upper()
    if not GSTIN_RE.match(g):
        return False
    return gstin_check_char(g[:14]) == g[14]


def norm_invoice_no(value: str) -> str:
    """'INV-00123', 'inv 123', '123' -> '123'. Used for duplicate detection only."""
    v = re.sub(r"[^A-Za-z0-9]", "", (value or "").upper())
    v = re.sub(r"^(INVOICE|INV|BILL|TAXINV|TI)", "", v)
    v = v.lstrip("0")
    return v or "0"


def norm_vehicle(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def norm_po(value: str) -> str:
    v = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    v = re.sub(r"^PO", "", v)
    return f"PO-{v}" if v else ""


def dec(value, places: str = "0.01") -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        return Decimal("0").quantize(Decimal(places))


def parse_date(value: str) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%b %Y", "%Y-%m"):
        try:
            from datetime import datetime

            parsed = datetime.strptime(value, fmt).date()
            return parsed
        except ValueError:
            continue
    return None


def pct_diff(actual: Decimal, expected: Decimal) -> Decimal:
    if expected == 0:
        return Decimal("0") if actual == 0 else Decimal("100")
    return ((actual - expected) / expected * 100).quantize(Decimal("0.01"))
