import asyncio
from datetime import date, timedelta

from bot.assess import prepare
from bot.db import (
    broker_history,
    latest_peer_stats,
    make_session_factory,
    save_broker_day,
)
from bot.peers.stats import compute_peer_stats, refresh_peer_stats
from bot.sectors.client import FIXTURES_DIR, SectorsClient, fixture_transport
from bot.snapshot.build import take_snapshot

AS_OF = date(2026, 9, 22)


def offline_client() -> SectorsClient:
    return SectorsClient("k", transport=fixture_transport(FIXTURES_DIR))


def member(close: float, volume: int, retail: tuple[int, int]) -> dict:
    daily = [
        {
            "date": (AS_OF - timedelta(days=i)).isoformat(),
            "open": close,
            "high": close,
            "low": close,
            "close": close + (i % 3),
            "volume": volume,
        }
        for i in range(30)
    ]
    composition = [
        {
            "date": "2026-07-31",
            "individual_l": retail[0],
            "individual_f": 0,
            "total_l": 100,
            "total_f": 0,
        },
        {
            "date": "2026-08-31",
            "individual_l": retail[1],
            "individual_f": 0,
            "total_l": 100,
            "total_f": 0,
        },
    ]
    return {"daily": daily, "composition": composition}


def test_compute_peer_stats_percentiles_and_screener_metrics():
    data = {f"S{i}": member(100 + i, 1000 * (i + 1), (10, 10 + i)) for i in range(6)}
    screener = {
        "npl_proxy": {
            "year": 2025,
            "values": {f"S{i}": -0.01 * (i + 1) for i in range(6)},
        },
        "nim": {"year": 2024, "values": {"S0": 0.05, "S1": None}},
    }

    stats = compute_peer_stats("Banks", AS_OF, data, screener, special=set())

    assert stats.members == 6
    assert stats.metrics["avg_daily_value"].n == 6
    assert stats.metrics["retail_shift"].p90 > 0
    assert stats.metrics["npl_proxy"].p10 > 0
    assert "nim" not in stats.metrics
    assert stats.years == {"npl_proxy": 2025, "nim": 2024}


def test_small_subsector_has_no_percentiles():
    data = {f"S{i}": member(100, 1000, (10, 11)) for i in range(3)}

    stats = compute_peer_stats("Tiny", AS_OF, data, {}, special=set())

    assert stats.metrics == {}


def test_refresh_peer_stats_from_fixtures_and_store():
    session_factory = make_session_factory("sqlite://")

    async def go():
        async with offline_client() as client:
            with session_factory() as session:
                return await refresh_peer_stats(
                    client, session, "Leisure Goods", False, AS_OF
                )

    stats = asyncio.run(go())

    assert stats.members == 5
    assert "retail_shift" in stats.metrics
    assert "avg_daily_value" not in stats.metrics
    assert stats.years["debt_to_equity"] == 2025
    with session_factory() as session:
        assert latest_peer_stats(session, "Leisure Goods", AS_OF) == stats
        assert (
            latest_peer_stats(session, "Leisure Goods", AS_OF - timedelta(days=1))
            is None
        )


def test_broker_days_round_trip_newest_last():
    session_factory = make_session_factory("sqlite://")
    body = {"end": "2026-09-18", "top_buyers": [], "top_sellers": []}
    with session_factory() as session:
        save_broker_day(session, "ANTM", date(2026, 9, 18), body)
        save_broker_day(
            session, "ANTM", date(2026, 9, 21), {**body, "end": "2026-09-21"}
        )
        save_broker_day(
            session, "ANTM", date(2026, 9, 22), {**body, "end": "2026-09-22"}
        )

        history = broker_history(session, "ANTM", before=AS_OF)

    assert [b.date for b in history] == [date(2026, 9, 18), date(2026, 9, 21)]


def test_snapshot_carries_sector_move_and_todays_broker():
    session_factory = make_session_factory("sqlite://")

    async def go():
        async with offline_client() as client:
            with session_factory() as session:
                snap, _ = await take_snapshot(client, session, "BIKE")
                return snap, broker_history(
                    session, "BIKE", before=AS_OF + timedelta(days=1)
                )

    snap, stored = asyncio.run(go())

    assert snap.sector_move.n == 4
    assert snap.sector_move.up + snap.sector_move.down <= 4
    assert [b.date for b in stored] == [AS_OF]


def test_prepare_fills_peers_and_broker_history_offline():
    session_factory = make_session_factory("sqlite://")

    async def go():
        async with offline_client() as client:
            with session_factory() as session:
                return await prepare(
                    client, session, "BIKE", fill_peers=True, fill_broker=True
                )

    snap = asyncio.run(go())

    days = sorted(
        f.stem for f in (FIXTURES_DIR / "broker-summary/BIKE/top").glob("*.json")
    )
    assert snap.peers is not None and snap.peers.sub_sector == "Leisure Goods"
    assert [b.date.isoformat() for b in snap.broker_history] == [
        d for d in days if d < AS_OF.isoformat()
    ]
    assert len(snap.broker_history) == 20


def test_prepare_without_filling_leaves_gaps():
    session_factory = make_session_factory("sqlite://")

    async def go():
        async with offline_client() as client:
            with session_factory() as session:
                return await prepare(
                    client, session, "BIKE", fill_peers=False, fill_broker=False
                )

    snap = asyncio.run(go())

    assert snap.peers is None
    assert snap.broker_history == []


def test_inactive_members_leave_price_distributions_but_not_retail():
    data = {f"S{i}": member(100 + i, 1000 * (i + 1), (10, 10 + i)) for i in range(6)}
    data["DEAD"] = member(50, 0, (10, 12))

    stats = compute_peer_stats("X", AS_OF, data, {}, special=set())

    assert stats.metrics["avg_daily_value"].n == 6
    assert stats.metrics["volatility_90d"].n == 6
    assert stats.metrics["retail_shift"].n == 7
    assert stats.metrics["avg_daily_value"].p10 > 0


def test_negative_ratios_are_excluded_from_distributions():
    values = {f"S{i}": 0.5 * (i + 1) for i in range(6)} | {"NEG": -88.0}
    screener = {
        "cost_to_income": {"year": 2025, "values": values},
        "debt_to_equity": {"year": 2025, "values": values},
    }

    stats = compute_peer_stats("X", AS_OF, {}, screener, special=set())

    assert stats.metrics["cost_to_income"].n == 6
    assert stats.metrics["debt_to_equity"].p10 > 0
