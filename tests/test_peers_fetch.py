import asyncio
from datetime import date

import httpx

from bot.peers.fetch import (
    fetch_broker_days,
    fetch_member_data,
    fetch_screener_metrics,
    history_dates,
    members,
)
from bot.sectors.client import SectorsClient
from bot.sectors.screener import slug
from bot.snapshot.models import Bar, Price
from tests.test_risk import fixture_snapshot

AS_OF = date(2026, 9, 22)


def client_for(handler) -> SectorsClient:
    return SectorsClient("k", transport=httpx.MockTransport(handler))


def test_members_come_from_local_ticker_list():
    banks = members("Banks")

    assert "BBCA" in banks and "BBRI" in banks
    assert banks == sorted(banks)
    assert len(members("Leisure Goods")) == 5


def test_slug_matches_sectors_screener_form():
    assert slug("Banks") == "banks"
    assert slug("Basic Materials") == "basic-materials"
    assert slug("Oil, Gas & Coal") == "oil-gas-coal"
    assert slug("Software & IT Services") == "software-it-services"


def screener_handler(values_by_year: dict[int, dict[str, float | None]], seen: list):
    def handler(request):
        order_by = request.url.params["order_by"].removeprefix("-")
        seen.append((request.url.params["where"], order_by))
        year = next((y for y in values_by_year if f"[{y}]" in order_by), None)
        values = values_by_year.get(year, {"AAA": 0.01, "BBB": -0.02})
        rows = [
            {"symbol": f"{s}.JK", "query_values": {order_by: v}}
            for s, v in values.items()
        ]
        return httpx.Response(
            200, json={"results": rows, "pagination": {"next_offset": None}}
        )

    return handler


def test_screener_metrics_map_symbols_to_expression_values():
    seen = []
    handler = screener_handler({2025: {"AAA": 0.5, "BBB": 1.5}}, seen)

    async def go():
        async with client_for(handler) as client:
            return await fetch_screener_metrics(client, "Basic Materials", False, AS_OF)

    metrics = asyncio.run(go())

    assert metrics["debt_to_equity"] == {
        "year": 2025,
        "values": {"AAA": 0.5, "BBB": 1.5},
    }
    assert set(metrics) == {"debt_to_equity", "accrual_ratio"}
    assert all(where == "sub_sector = 'basic-materials'" for where, _ in seen)


def test_screener_year_falls_back_when_majority_is_null():
    seen = []
    handler = screener_handler(
        {
            2025: {"AAA": None, "BBB": None, "CCC": 0.1},
            2024: {"AAA": 0.2, "BBB": 0.3, "CCC": 0.1},
        },
        seen,
    )

    async def go():
        async with client_for(handler) as client:
            return await fetch_screener_metrics(client, "Banks", True, AS_OF)

    metrics = asyncio.run(go())

    assert metrics["cost_to_income"]["year"] == 2024
    assert set(metrics) == {"npl_proxy", "cost_to_income", "nim"}


def test_member_data_fetches_daily_window_and_composition():
    seen = []

    def handler(request):
        seen.append((request.url.path, dict(request.url.params)))
        if "daily" in request.url.path:
            return httpx.Response(200, json=[{"date": "2026-09-22", "close": 1}])
        return httpx.Response(200, json={"data": [{"date": "2026-08-31"}] * 2})

    async def go():
        async with client_for(handler) as client:
            return await fetch_member_data(client, ["AAA", "BBB"], AS_OF)

    data = asyncio.run(go())

    assert set(data) == {"AAA", "BBB"}
    assert data["AAA"]["daily"] == [{"date": "2026-09-22", "close": 1}]
    daily = next(p for path, p in seen if path == "/v2/daily/AAA/")
    assert daily == {"start": "2026-06-24", "end": "2026-09-22"}


def test_history_dates_take_last_trading_days_before_as_of():
    snap = fixture_snapshot("ANTM")

    days = history_dates(snap, 20)

    assert len(days) == 20
    assert days == sorted(days)
    assert AS_OF not in days
    assert days[-1] == max(b.date for b in snap.price.bars if b.date < AS_OF)


def test_history_dates_short_price_series():
    snap = fixture_snapshot("ANTM").model_copy(
        update={
            "price": Price(
                bars=[
                    Bar(date=date(2026, 9, d), open=1, high=1, low=1, close=1, volume=1)
                    for d in (18, 21, 22)
                ],
                splits=[],
            )
        }
    )

    assert history_dates(snap, 20) == [date(2026, 9, 18), date(2026, 9, 21)]


def test_broker_days_request_each_date():
    seen = []

    def handler(request):
        seen.append(request.url.params["start"])
        return httpx.Response(200, json={"end": request.url.params["end"]})

    async def go():
        async with client_for(handler) as client:
            return await fetch_broker_days(
                client, "ANTM", [date(2026, 9, 18), date(2026, 9, 21)]
            )

    result = asyncio.run(go())

    assert sorted(seen) == ["2026-09-18", "2026-09-21"]
    assert result[date(2026, 9, 21)] == {"end": "2026-09-21"}


def test_one_failed_request_keeps_the_other_paid_results():
    def handler(request):
        if request.url.path == "/v2/daily/BBB/":
            return httpx.Response(503, json={"error": "UNAVAILABLE"})
        if request.url.params.get("start") == "2026-09-18":
            return httpx.Response(502, json={"error": "BAD_GATEWAY"})
        if "daily" in request.url.path:
            return httpx.Response(200, json=[{"date": "2026-09-22", "close": 1}])
        if "broker-summary" in request.url.path:
            return httpx.Response(200, json={"end": request.url.params["start"]})
        return httpx.Response(200, json={"data": []})

    async def go():
        client = SectorsClient(
            "k", transport=httpx.MockTransport(handler), retry_delays=()
        )
        async with client:
            members = await fetch_member_data(client, ["AAA", "BBB"], AS_OF)
            days = await fetch_broker_days(
                client, "AAA", [date(2026, 9, 18), date(2026, 9, 21)]
            )
        return members, days

    members, days = asyncio.run(go())

    assert set(members) == {"AAA"}
    assert set(days) == {date(2026, 9, 21)}
