import asyncio
import copy
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from bot.db import get_snapshot, make_session_factory, save_snapshot
from bot.sectors.client import FIXTURES_DIR, SectorsClient, fixture_transport
from bot.snapshot.build import (
    fetch_eod,
    fetch_events,
    flatten,
    free_float,
    normalize,
    normalize_broker,
    normalize_corporate_actions,
    normalize_events,
    normalize_financials,
    normalize_holders,
    normalize_ownership,
    normalize_price,
    take_snapshot,
)
from bot.tickers import valid_ticker


def load(rel: str):
    return json.loads((FIXTURES_DIR / f"{rel}.json").read_text())


def raw_for(symbol: str) -> dict:
    async def go():
        async with SectorsClient("k", transport=fixture_transport(FIXTURES_DIR)) as c:
            report = await c.get(f"/company/report/{symbol}/")
            as_of = date.fromisoformat(report["overview"]["latest_close_date"])
            return {
                "report": report,
                **await fetch_eod(c, symbol, as_of),
                **await fetch_events(c, symbol, as_of),
            }

    return asyncio.run(go())


SOURCES = [{"endpoint": "/x/", "fetched_at": "2026-09-23T00:00:00+00:00", "credits": 4}]


def test_normalize_header_and_overview_antm():
    snap = normalize(raw_for("ANTM"), SOURCES)

    assert snap.symbol == "ANTM"
    assert snap.as_of == date(2026, 9, 22)
    assert snap.listing_board == "Main"
    assert snap.sub_sector == "Basic Materials"
    assert snap.overview.company_name == "Aneka Tambang Tbk."
    assert snap.overview.market_cap == 76177524178250
    assert snap.sources[0].credits == 4


def test_normalize_valuation_history_ascending():
    snap = normalize(raw_for("ANTM"), SOURCES)

    years = [row["year"] for row in snap.valuation.history]
    assert years == sorted(years)
    assert snap.valuation.history[-1]["pe_peer_avg"] is not None


def test_valid_ticker():
    assert valid_ticker(" antm ") == "ANTM"
    assert valid_ticker("ANTM.JK") == "ANTM"
    assert valid_ticker("XXXX") is None


def test_db_round_trip():
    session_factory = make_session_factory("sqlite://")
    snap = normalize(raw_for("ANTM"), SOURCES)

    with session_factory() as session:
        save_snapshot(session, snap)
        loaded = get_snapshot(session, "ANTM", date(2026, 9, 22))

    assert loaded == snap
    with session_factory() as session:
        assert get_snapshot(session, "ANTM", date(2026, 9, 21)) is None


def counting_offline_client() -> tuple[SectorsClient, list]:
    requests = []
    inner = fixture_transport(FIXTURES_DIR)

    def handler(request):
        requests.append(request.url.path)
        return inner.handle_request(request)

    return SectorsClient("k", transport=httpx.MockTransport(handler)), requests


def test_take_snapshot_saves_then_uses_cache():
    session_factory = make_session_factory("sqlite://")

    async def go():
        client, requests = counting_offline_client()
        async with client:
            with session_factory() as session:
                first, first_cached = await take_snapshot(client, session, "ANTM")
            calls_first = len(requests)
            with session_factory() as session:
                second, second_cached = await take_snapshot(client, session, "ANTM")
        return first, first_cached, second, second_cached, calls_first, requests

    first, first_cached, second, second_cached, calls_first, requests = asyncio.run(
        go()
    )
    assert not first_cached
    assert second_cached
    assert second.model_copy(update={"sources": []}) == first.model_copy(
        update={"sources": []}
    )
    assert sorted(requests[calls_first:]) == [
        "/v2/company/report/ANTM/",
        "/v2/filings/",
        "/v2/news/",
        "/v2/suspensions/",
    ]
    assert len(second.sources) == len(first.sources)


def test_take_snapshot_rejects_unknown_ticker_without_requests():
    session_factory = make_session_factory("sqlite://")

    async def go():
        client, requests = counting_offline_client()
        async with client:
            with session_factory() as session, pytest.raises(ValueError):
                await take_snapshot(client, session, "XXXX")
        return requests

    assert asyncio.run(go()) == []


AS_OF = date(2026, 9, 22)


def bar(day: str, close: int) -> dict:
    return {
        "date": day,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 100,
        "market_cap": 1,
    }


def test_price_bars_ascending_within_window_antm():
    price = normalize_price(
        load("daily/ANTM"), load("company/corporate-actions/ANTM"), AS_OF
    )

    dates = [b.date for b in price.bars]
    assert len(dates) == 63
    assert dates == sorted(set(dates))
    assert dates[0] == date(2026, 6, 24) and dates[-1] == AS_OF
    assert price.splits == []


def test_price_sorts_dedupes_and_drops_out_of_window():
    rows = [
        bar("2026-09-22", 3),
        bar("2026-05-01", 1),
        bar("2026-09-21", 2),
        bar("2026-09-22", 4),
        bar("2026-09-23", 5),
    ]

    price = normalize_price(rows, {"corporate_actions": {"stock_split": None}}, AS_OF)

    assert [(b.date.isoformat(), b.close) for b in price.bars] == [
        ("2026-09-21", 2),
        ("2026-09-22", 4),
    ]


def test_splits_sorted_by_ex_date():
    ca = {
        "corporate_actions": {
            "stock_split": [
                {"ex_date": "2026-02-01", "ratio": 2},
                {"ex_date": "2025-01-01", "ratio": 5},
            ]
        }
    }

    price = normalize_price([], ca, AS_OF)

    assert [s["ex_date"] for s in price.splits] == ["2025-01-01", "2026-02-01"]


def test_full_snapshot_has_price():
    snap = normalize(raw_for("ANTM"), SOURCES)

    assert snap.price.bars[-1].close == 3170


def financials_for(symbol: str):
    return normalize_financials(
        load(f"company/report/{symbol}")["financials"],
        load(f"financials/quarterly/{symbol}"),
    )


def test_annual_financials_ascending_and_nulls_kept_antm():
    fin = financials_for("ANTM")

    years = [row["year"] for row in fin.annual]
    assert years == sorted(years) and years[-1] == 2025
    assert fin.annual[0]["retained_earnings"] is None
    assert fin.eps == 299.98354536343203


def test_ratios_flattened_antm():
    latest = financials_for("ANTM").annual_ratios[-1]

    assert latest["year"] == 2025
    assert latest["debt_to_equity_ratio"] == 0.43526143769956005
    assert "leverage" not in latest


def test_quarterly_ascending_with_unified_names_antm():
    quarters = financials_for("ANTM").quarterly

    dates = [q["date"] for q in quarters]
    assert dates == sorted(dates)
    assert (
        "current_assets" in quarters[-1] and "total_current_asset" not in quarters[-1]
    )
    assert "symbol" not in quarters[-1]


def test_bank_ratios_and_sector_metrics_bbca():
    fin = financials_for("BBCA")

    latest = fin.annual_ratios[-1]
    assert latest["capital_adequacy_ratio"] == 0.30367508951660466
    assert latest["loan_to_deposit_ratio"] == 0.7593527811195531
    quarter = fin.quarterly[-1]
    assert quarter["gross_loan"] == 1012705846000000
    assert quarter["allowance_for_loans"] == 30705949000000
    assert quarter["gross_profit"] is None


def test_flatten_rejects_name_collision():
    with pytest.raises(ValueError, match="roa"):
        flatten({"a": {"roa": 1}, "b": {"roa": 2}})


def test_free_float_from_public_row():
    holders = normalize_holders(
        load("company/report/ANTM")["ownership"]["major_shareholders"]
    )

    assert holders[0].share == 0.65
    assert free_float(holders) == 0.35
    assert (
        free_float(normalize_holders([{"name": "PT A", "share_percentage": "0.9"}]))
        is None
    )


def test_acceleration_board_free_float_aegs():
    report = load("company/report/AEGS")

    assert report["overview"]["listing_board"] == "Acceleration"
    assert (
        free_float(normalize_holders(report["ownership"]["major_shareholders"]))
        == 0.3977
    )


def filing(ts: str, pct: float, holder_type: str = "insider") -> dict:
    return {
        "timestamp": ts,
        "holder_type": holder_type,
        "transaction_type": "sell",
        "share_percentage_before": pct,
        "share_percentage_after": 0.0,
        "share_percentage_transaction": pct,
        "symbol": "ANTM.JK",
    }


def test_insider_filings_window_type_and_percent_to_fraction():
    rows = [
        filing("2026-09-01T10:00:00", 0.03),
        filing("2026-06-01T10:00:00", 1.0),
        filing("2026-08-01T10:00:00", 0.5),
        filing("2026-09-02T10:00:00", 2.0, "institution"),
    ]

    own = normalize_ownership(load("company/report/ANTM")["ownership"], [], rows, AS_OF)

    assert [f["timestamp"] for f in own.insider_filings] == [
        "2026-08-01T10:00:00",
        "2026-09-01T10:00:00",
    ]
    assert own.insider_filings[-1]["share_percentage_transaction"] == 0.0003
    assert "symbol" not in own.insider_filings[-1]


def test_real_insider_filings_outside_window_antm():
    own = normalize_ownership(
        load("company/report/ANTM")["ownership"],
        [],
        load("filings/ANTM")["results"],
        AS_OF,
    )

    assert own.insider_filings == []


def test_composition_ascending_and_deduped():
    data = load("company/shareholders-composition/ANTM")["data"]

    own = normalize_ownership(
        load("company/report/ANTM")["ownership"], data + data, [], AS_OF
    )

    dates = [row["date"] for row in own.composition]
    assert dates == sorted(set(dates)) and len(dates) == 8


def test_broker_sorted_by_rank():
    body = load("broker-summary/ANTM/top")
    body["top_buyers"].reverse()

    broker = normalize_broker(body)

    assert broker.date == AS_OF
    assert [b["rank"] for b in broker.top_buyers] == list(range(1, 11))
    assert broker.top_sellers[0]["net_idr"] < 0


def test_full_snapshot_has_ownership_and_broker():
    snap = normalize(raw_for("ANTM"), SOURCES)

    assert snap.overview.free_float == 0.35
    assert len(snap.ownership.composition) == 8
    assert snap.broker.top_buyers[0]["broker_code"] == "PD"


def test_corporate_actions_sorted_and_nulls_become_empty_antm():
    ca = normalize_corporate_actions(load("company/corporate-actions/ANTM"))

    ex_dates = [d["ex_date"] for d in ca["dividend"]]
    assert ex_dates == sorted(ex_dates) and ex_dates[-1] == "2026-06-22"
    assert ca["warrant"] == [] and ca["bonus"] == [] and ca["stock_split"] == []
    agm_dates = [a["agm_date"] for a in ca["agm"]]
    assert agm_dates == sorted(agm_dates)


def test_news_only_for_symbol_within_window_ascending():
    articles = load("news")["results"] + [
        {"timestamp": "2026-07-01T09:00:00", "symbols": ["ANTM.JK"], "tags": []}
    ]

    events = normalize_events(
        "ANTM", articles, [], load("company/corporate-actions/ANTM"), AS_OF
    )

    assert events.news, "fixture berita memuat artikel ANTM"
    assert all("ANTM" in a["symbols"] for a in events.news)
    stamps = [a["timestamp"] for a in events.news]
    assert stamps == sorted(stamps) and stamps[0] >= "2026-08-23"


def test_suspensions_only_for_symbol_within_window():
    rows = [
        {"symbol": "NASI.JK", "suspension_date": "2026-09-22", "reason": "a"},
        {"symbol": "NASI.JK", "suspension_date": "2026-05-01", "reason": "lama"},
        {"symbol": "WAPO.JK", "suspension_date": "2026-09-22", "reason": "b"},
        {"symbol": "NASI.JK", "suspension_date": "2026-09-01", "reason": "c"},
    ]

    events = normalize_events("NASI", [], rows, {"corporate_actions": {}}, AS_OF)

    assert [s["reason"] for s in events.suspensions] == ["c", "a"]


def test_full_snapshot_has_events():
    snap = normalize(raw_for("ANTM"), SOURCES)

    assert snap.events.suspensions == []
    assert snap.events.corporate_actions["dividend"]


def test_normalize_is_deterministic_and_ignores_input_order():
    raw = raw_for("ANTM")
    shuffled = copy.deepcopy(raw)
    shuffled["daily"].reverse()
    shuffled["quarterly"].reverse()
    shuffled["composition"].reverse()
    shuffled["news"].reverse()
    shuffled["report"]["financials"]["historical_financials"].reverse()
    shuffled["report"]["valuation"]["historical_valuation"].reverse()
    shuffled["corporate_actions"]["corporate_actions"]["dividend"].reverse()

    first = normalize(raw, SOURCES).model_dump_json()

    assert normalize(raw, SOURCES).model_dump_json() == first
    assert normalize(shuffled, SOURCES).model_dump_json() == first


def test_nulls_are_never_replaced_with_zero():
    raw = raw_for("ANTM")
    snap = normalize(raw, SOURCES)

    annual = {row["year"]: row for row in snap.financials.annual}
    for row in raw["report"]["financials"]["historical_financials"]:
        for key, value in row.items():
            if value is None:
                assert annual[row["year"]][key] is None, (row["year"], key)
    quarters = {q["date"]: q for q in snap.financials.quarterly}
    for q in raw["quarterly"]:
        for key, value in q.items():
            if value is None and key != "financials_sector_metrics":
                assert quarters[q["date"]][key] is None, (q["date"], key)


def test_fixtures_do_not_contain_api_key():
    env = Path(__file__).resolve().parents[1] / ".env"
    lines = env.read_text().splitlines() if env.exists() else []
    key = next(
        (ln.split("=", 1)[1] for ln in lines if ln.startswith("SECTORS_API_KEY=")), ""
    )
    if not key:
        pytest.skip("SECTORS_API_KEY tidak ada di .env")

    for file in (Path(__file__).parent / "fixtures").rglob("*.json"):
        assert key not in file.read_text(), file


def test_future_dated_suspension_is_kept():
    # Diumumkan 21 Sep, berlaku 22 Sep; putaran 06.00 tanggal 22 memakai as_of 21.
    rows = load("suspensions")["results"]

    events = normalize_events(
        "NASI", [], rows, {"corporate_actions": {}}, date(2026, 9, 21)
    )

    assert [s["suspension_date"] for s in events.suspensions] == ["2026-09-22"]


def test_cache_hit_refreshes_events():
    session_factory = make_session_factory("sqlite://")
    news_calls = []
    inner = fixture_transport(FIXTURES_DIR)

    def handler(request):
        if request.url.path == "/v2/news/":
            news_calls.append(1)
            if len(news_calls) > 1:
                return httpx.Response(
                    200, json={"results": [], "pagination": {"next_offset": None}}
                )
        return inner.handle_request(request)

    async def go():
        async with SectorsClient("k", transport=httpx.MockTransport(handler)) as c:
            with session_factory() as session:
                first, _ = await take_snapshot(c, session, "ANTM")
            with session_factory() as session:
                second, cached = await take_snapshot(c, session, "ANTM")
                stored = get_snapshot(session, "ANTM", AS_OF)
        return first, second, cached, stored

    first, second, cached, stored = asyncio.run(go())
    assert cached
    assert first.events.news and second.events.news == []
    assert stored == second
    assert second.price == first.price


def test_sources_are_per_snapshot_on_shared_client():
    async def go():
        async with SectorsClient("k", transport=fixture_transport(FIXTURES_DIR)) as c:
            snaps = []
            for _ in range(2):
                with make_session_factory("sqlite://")() as session:
                    snaps.append((await take_snapshot(c, session, "ANTM"))[0])
        return snaps

    first, second = asyncio.run(go())
    assert len(first.sources) == len(second.sources) == 9


def test_save_snapshot_twice_same_date_upserts():
    session_factory = make_session_factory("sqlite://")
    snap = normalize(raw_for("ANTM"), SOURCES)
    newer = snap.model_copy(update={"sector": "Diperbarui"})

    with session_factory() as session:
        save_snapshot(session, snap)
        save_snapshot(session, newer)
        assert get_snapshot(session, "ANTM", AS_OF).sector == "Diperbarui"


def test_missing_data_404_becomes_empty_section():
    inner = fixture_transport(FIXTURES_DIR)

    def handler(request):
        if request.url.path == "/v2/broker-summary/ANTM/top/":
            return httpx.Response(
                404, json={"error": "NOT_FOUND", "message": "no data"}
            )
        return inner.handle_request(request)

    async def go():
        async with SectorsClient("k", transport=httpx.MockTransport(handler)) as c:
            with make_session_factory("sqlite://")() as session:
                return (await take_snapshot(c, session, "ANTM"))[0]

    snap = asyncio.run(go())
    assert snap.broker.top_buyers == [] and snap.broker.date == AS_OF


def test_real_split_schema_sorted_by_date_bbca():
    ca = load("company/corporate-actions/BBCA")
    ca["corporate_actions"]["stock_split"].insert(
        0, {"date": "2024-01-01", "split_ratio": 2}
    )

    price = normalize_price([], ca, AS_OF)

    assert [s["date"] for s in price.splits] == ["2021-10-13", "2024-01-01"]
