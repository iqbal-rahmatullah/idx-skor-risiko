import asyncio
import logging
from collections.abc import Awaitable, Hashable
from datetime import date
from typing import Any, TypeVar

from bot.sectors.client import SectorsClient
from bot.sectors.screener import fetch_screener_metric
from bot.snapshot.build import DAILY_WINDOW, fetch_composition
from bot.snapshot.models import TickerSnapshot
from bot.tickers import TICKERS

log = logging.getLogger(__name__)
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

CONCURRENCY = 4
BANK_EXPRESSIONS = {
    "npl_proxy": "(allowance_for_loans[{y}]/gross_loan[{y}])",
    "cost_to_income": "cost_to_income_ratio[{y}]",
    "nim": "net_interest_margin[{y}]",
}
NONBANK_EXPRESSIONS = {
    "debt_to_equity": "debt_to_equity_ratio[{y}]",
    "accrual_ratio": (
        "((earnings[{y}]-operating_cash_flow[{y}])"
        "/((total_assets[{y}]+total_assets[{py}])/2))"
    ),
}


def members(sub_sector: str) -> list[str]:
    return sorted(s for s, v in TICKERS.items() if v["sub_sector"] == sub_sector)


def mostly_filled(values: dict[str, float | None]) -> bool:
    return bool(values) and 2 * sum(v is not None for v in values.values()) >= len(
        values
    )


def history_dates(snap: TickerSnapshot, n: int) -> list[date]:
    return [b.date for b in snap.price.bars if b.date < snap.as_of][-n:]


async def settled(jobs: dict[K, Awaitable[tuple[K, V]]]) -> dict[K, V]:
    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    done = {}
    for key, result in zip(jobs, results, strict=True):
        if isinstance(result, Exception):
            log.warning("permintaan %s gagal: %s", key, type(result).__name__)
        elif isinstance(result, BaseException):
            raise result
        else:
            done[key] = result[1]
    return done


async def fetch_member_data(
    client: SectorsClient, symbols: list[str], as_of: date
) -> dict[str, dict[str, Any]]:
    gate = asyncio.Semaphore(CONCURRENCY)
    start = (as_of - DAILY_WINDOW).isoformat()

    async def one(symbol: str) -> tuple[str, dict[str, Any]]:
        async with gate:
            daily = await client.get(
                f"/daily/{symbol}/",
                missing_ok=True,
                start=start,
                end=as_of.isoformat(),
            )
            composition = await fetch_composition(client, symbol, as_of)
        return symbol, {"daily": daily or [], "composition": composition}

    return await settled(dict(zip(symbols, map(one, symbols), strict=True)))


async def fetch_screener_metrics(
    client: SectorsClient, sub_sector: str, financial: bool, as_of: date
) -> dict[str, dict[str, Any]]:
    templates = BANK_EXPRESSIONS if financial else NONBANK_EXPRESSIONS
    metrics: dict[str, dict[str, Any]] = {}
    for name, template in templates.items():
        for year in (as_of.year - 1, as_of.year - 2):
            expression = template.format(y=year, py=year - 1)
            values = await fetch_screener_metric(client, sub_sector, expression)
            if mostly_filled(values):
                break
        metrics[name] = {"year": year, "values": values}
    return metrics


async def fetch_broker_days(
    client: SectorsClient, symbol: str, days: list[date]
) -> dict[date, dict[str, Any] | None]:
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(day: date) -> tuple[date, dict[str, Any] | None]:
        async with gate:
            body = await client.get(
                f"/broker-summary/{symbol}/top/",
                missing_ok=True,
                start=day.isoformat(),
                end=day.isoformat(),
                n_brokers=10,
            )
        return day, body

    return await settled(dict(zip(days, map(one, days), strict=True)))
