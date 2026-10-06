from datetime import date
from decimal import ROUND_HALF_UP, Decimal

IDR_UNITS = ((10**12, "triliun"), (10**9, "miliar"), (10**6, "juta"))
MONTHS = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)


def num(x: float, decimals: int = 2) -> str:
    q = Decimal(repr(x)).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    whole, _, frac = f"{q:,}".partition(".")
    frac = frac.rstrip("0")
    whole = whole.replace(",", ".")
    return f"{whole},{frac}" if frac else whole


def pct(x: float) -> str:
    return f"{num(x * 100)}%"


def idr(x: float) -> str:
    if x < 0:
        return f"-{idr(-x)}"
    for size, unit in IDR_UNITS:
        if x >= size:
            return f"Rp{num(x / size)} {unit}"
    return f"Rp{num(x, 0)}"


def shares(x: float) -> str:
    return f"{num(x, 0)} lembar"


def day(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def points(x: float) -> str:
    return f"{'+' if x > 0 else ''}{num(x * 100)} poin persen"
