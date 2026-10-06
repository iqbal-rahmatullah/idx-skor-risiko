from datetime import date
from itertools import pairwise
from statistics import mean, quantiles, stdev
from typing import Any

from bot.risk import thresholds as t
from bot.snapshot.models import Bar, Percentiles


def percentiles(values: list[float | None]) -> Percentiles | None:
    sample = sorted(v for v in values if v is not None)
    if len(sample) < t.PERCENTILE_MIN_SAMPLE:
        return None
    cuts = quantiles(sample, n=100, method="inclusive")
    return Percentiles(
        n=len(sample), **{f"p{k}": cuts[k - 1] for k in t.PERCENTILE_LEVELS}
    )


def avg_daily_value(bars: list[Bar]) -> float | None:
    rows = [b for b in bars if b.close is not None and b.volume is not None]
    return sum(b.close * b.volume for b in rows) / len(rows) if rows else None


def closes(bars: list[Bar]) -> list[float]:
    return [b.close for b in bars if b.close is not None]


def rsd(values: list[float]) -> float | None:
    if len(values) < 2 or not mean(values):
        return None
    return stdev(values) / mean(values)


def max_drawdown(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    peak, deepest = values[0], 0.0
    for value in values:
        peak = max(peak, value)
        deepest = min(deepest, value / peak - 1)
    return abs(deepest)


def daily_returns(values: list[float]) -> list[float]:
    return [cur / prev - 1 for prev, cur in pairwise(values) if prev]


def adjust_for_splits(
    bars: list[Bar], splits: list[dict[str, Any]]
) -> list[Bar] | None:
    if not bars:
        return bars
    adjusted = list(bars)
    for split in splits:
        raw_date = split.get("date") or split.get("ex_date")
        if raw_date is None:
            return None
        day = date.fromisoformat(str(raw_date)[:10])
        if not bars[0].date < day <= bars[-1].date:
            continue
        ratio = split.get("split_ratio")
        if not ratio:
            return None
        adjusted = [
            b.model_copy(
                update={
                    "open": b.open and b.open / ratio,
                    "high": b.high and b.high / ratio,
                    "low": b.low and b.low / ratio,
                    "close": b.close and b.close / ratio,
                    "volume": b.volume and round(b.volume * ratio),
                }
            )
            if b.date < day
            else b
            for b in adjusted
        ]
    return adjusted


def tick(price: float) -> int:
    return next(size for upper, size in t.TICK_SIZES if price < upper)


def trading_limits(price: float, special: bool) -> tuple[float, float]:
    if special:
        return t.SPECIAL_BOARD_LIMIT, t.SPECIAL_BOARD_LIMIT
    return next(pct for upper, pct in t.ARA_BANDS if price <= upper), t.ARB_REGULAR


def limit_touches(bars: list[Bar], special: bool) -> int | None:
    window = [b for b in bars if b.close is not None][-(t.LIMIT_TOUCH_DAYS + 1) :]
    if len(window) < t.LIMIT_TOUCH_DAYS + 1:
        return None
    touches = 0
    for prev, cur in pairwise(window):
        up, down = trading_limits(prev.close, special)
        upper = prev.close * (1 + up)
        lower = prev.close * (1 - down)
        high = cur.high if cur.high is not None else cur.close
        low = cur.low if cur.low is not None else cur.close
        if high >= upper - tick(upper) or low <= lower + tick(lower):
            touches += 1
    return touches


def retail_share(row: dict[str, Any]) -> float | None:
    fields = ("individual_l", "individual_f", "total_l", "total_f")
    if any(row.get(f) is None for f in fields):
        return None
    total = row["total_l"] + row["total_f"]
    return (row["individual_l"] + row["individual_f"]) / total if total else None


def retail_shift(rows: list[dict[str, Any]]) -> float | None:
    ordered = sorted(rows, key=lambda r: r["date"])
    if len(ordered) < 2:
        return None
    latest, previous = retail_share(ordered[-1]), retail_share(ordered[-2])
    if latest is None or previous is None:
        return None
    return latest - previous
