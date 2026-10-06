from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from bot.db import save_peer_stats
from bot.idx.lists import notation_rows
from bot.peers.fetch import fetch_member_data, fetch_screener_metrics, members
from bot.risk.measures import (
    avg_daily_value,
    closes,
    limit_touches,
    max_drawdown,
    percentiles,
    retail_shift,
    rsd,
)
from bot.sectors.client import SectorsClient
from bot.snapshot.build import bars_from_rows
from bot.snapshot.models import PeerStats
from bot.tickers import TICKERS

MEMBER_METRICS = (
    "avg_daily_value",
    "volatility_90d",
    "drawdown_90d",
    "ara_arb_touches",
    "retail_shift",
)
PRICE_METRICS = ("avg_daily_value", "volatility_90d", "drawdown_90d", "ara_arb_touches")
ABSOLUTE_METRICS = frozenset({"npl_proxy"})
NONNEGATIVE_METRICS = frozenset({"debt_to_equity", "cost_to_income"})


def member_metrics(
    data: dict[str, Any], as_of: date, special: bool
) -> dict[str, float | None]:
    bars = bars_from_rows(data["daily"], as_of)
    series = closes(bars)
    metrics = {
        "avg_daily_value": avg_daily_value(bars),
        "volatility_90d": rsd(series),
        "drawdown_90d": max_drawdown(series),
        "ara_arb_touches": limit_touches(bars, special),
        "retail_shift": retail_shift(data["composition"]),
    }
    if not any(b.volume for b in bars):
        metrics |= dict.fromkeys(PRICE_METRICS)
    return metrics


def compute_peer_stats(
    sub_sector: str,
    as_of: date,
    member_data: dict[str, dict[str, Any]],
    screener: dict[str, dict[str, Any]],
    special: set[str],
) -> PeerStats:
    per_member = [
        member_metrics(data, as_of, symbol in special)
        for symbol, data in sorted(member_data.items())
    ]
    metrics = {
        name: percentiles([m[name] for m in per_member]) for name in MEMBER_METRICS
    }
    for name, entry in sorted(screener.items()):
        values = list(entry["values"].values())
        if name in ABSOLUTE_METRICS:
            values = [None if v is None else abs(v) for v in values]
        if name in NONNEGATIVE_METRICS:
            values = [v for v in values if v is not None and v >= 0]
        metrics[name] = percentiles(values)
    return PeerStats(
        sub_sector=sub_sector,
        as_of=as_of,
        members=len(member_data),
        metrics={k: v for k, v in metrics.items() if v is not None},
        years={name: entry["year"] for name, entry in sorted(screener.items())},
    )


def special_symbols(symbols: list[str]) -> set[str]:
    rows = notation_rows() or []
    monitored = {r["kode"] for r in rows if "X" in r["notasi"].split(",")}
    return {
        s
        for s in symbols
        if s in monitored or TICKERS.get(s, {}).get("listing_board") == "Acceleration"
    }


async def refresh_peer_stats(
    client: SectorsClient,
    session: Session,
    sub_sector: str,
    financial: bool,
    as_of: date,
) -> PeerStats:
    group = members(sub_sector)
    data = await fetch_member_data(client, group, as_of)
    screener = await fetch_screener_metrics(client, sub_sector, financial, as_of)
    stats = compute_peer_stats(
        sub_sector, as_of, data, screener, special_symbols(group)
    )
    save_peer_stats(session, stats)
    return stats
