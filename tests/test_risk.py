import asyncio
import copy
import json
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from bot.db import make_session_factory
from bot.idx.lists import idx_lists_for
from bot.risk.build_json import build_indicators, dumps
from bot.risk.format import day, idr, pct
from bot.risk.indicators.p1_ukuran import daily_liquidity, free_float, sub_51_price
from bot.risk.indicators.p2_keuangan import car, ldr_rim, negative_equity, no_revenue
from bot.risk.indicators.p6_peristiwa import (
    special_monitoring_board,
    special_notation,
    suspension_uma,
)
from bot.risk.score import final_score, grade, pillar_score
from bot.sectors.client import FIXTURES_DIR, SectorsClient, fixture_transport
from bot.snapshot.build import normalize, normalize_suspensions, take_snapshot
from bot.snapshot.models import Bar, IdxLists, Price, TickerSnapshot
from tests.test_snapshot import raw_for

BIG_CAP = 76_177_524_178_250
SMALL_CAP = 1_000_000_000_000


@cache
def fixture_snapshot(symbol: str) -> TickerSnapshot:
    async def go():
        async with SectorsClient("k", transport=fixture_transport(FIXTURES_DIR)) as c:
            with make_session_factory("sqlite://")() as session:
                return (await take_snapshot(c, session, symbol))[0]

    return asyncio.run(go())


def with_overview(snap: TickerSnapshot, board: str | None = None, **overview):
    update = {"overview": snap.overview.model_copy(update=overview)}
    if board:
        update["listing_board"] = board
    return snap.model_copy(update=update)


def test_pct_and_idr_use_indonesian_format():
    assert pct(0.35) == "35%"
    assert pct(0.075) == "7,5%"
    assert pct(0.3977) == "39,77%"
    assert idr(5_000_000) == "Rp5 juta"
    assert idr(12_345_000_000) == "Rp12,35 miliar"
    assert day(date(2028, 3, 31)) == "31 Maret 2028"


def test_free_float_real_antm_is_wajar():
    ind = free_float(fixture_snapshot("ANTM"))

    assert ind.status == "wajar"
    assert ind.value == 0.35
    assert ind.display == "35%"
    assert ind.source_type == "regulator"
    assert ind.evidence_path == "overview.free_float"


@pytest.mark.parametrize(
    ("board", "cap", "value", "status"),
    [
        ("Main", BIG_CAP, 0.10, "bermasalah"),
        ("Main", BIG_CAP, 0.13, "perhatian"),
        ("Development", BIG_CAP, 0.15, "wajar"),
        ("Main", SMALL_CAP, 0.10, "perhatian"),
        ("Main", SMALL_CAP, 0.15, "wajar"),
        ("Acceleration", SMALL_CAP, 0.05, "bermasalah"),
        ("Acceleration", SMALL_CAP, 0.10, "wajar"),
        ("Acceleration", SMALL_CAP, 0.3977, "wajar"),
        ("Watchlist", SMALL_CAP, 0.10, "bermasalah"),
        ("New Economy", SMALL_CAP, 0.13, "perhatian"),
    ],
)
def test_free_float_bands(board, cap, value, status):
    snap = with_overview(
        fixture_snapshot("ANTM"), board, market_cap=cap, free_float=value
    )

    assert free_float(snap).status == status


def test_free_float_after_transition_is_binary_at_15_percent():
    snap = with_overview(
        fixture_snapshot("ANTM"), "Main", market_cap=SMALL_CAP, free_float=0.13
    ).model_copy(update={"as_of": date(2029, 4, 1)})

    assert free_float(snap).status == "bermasalah"


def test_free_float_missing_is_tidak_tersedia():
    ind = free_float(with_overview(fixture_snapshot("ANTM"), free_float=None))

    assert ind.status == "tidak_tersedia"
    assert ind.value is None


def test_pillar_score_counts_only_bermasalah_over_assessable_weights():
    snap = with_overview(fixture_snapshot("ANTM"), "Main", free_float=0.10)
    bad = free_float(snap)
    good = free_float(fixture_snapshot("ANTM"))
    missing = free_float(with_overview(fixture_snapshot("ANTM"), free_float=None))

    assert pillar_score([bad, good]) == 50
    assert pillar_score([bad, missing]) == 100
    assert pillar_score([missing]) is None
    assert pillar_score([]) is None


def test_final_score_skips_empty_pillars_and_rounds_half_up():
    assert final_score([50, None, 0]) == 25
    assert final_score([None, None]) is None
    assert final_score([20.5]) == 21


@pytest.mark.parametrize(
    ("score", "letter"),
    [
        (0, "A"),
        (20, "A"),
        (21, "B"),
        (40, "B"),
        (41, "C"),
        (80, "D"),
        (81, "E"),
        (100, "E"),
    ],
)
def test_grade_boundaries(score, letter):
    assert grade(score) == letter


def test_grade_none_without_score():
    assert grade(None) is None


def test_indicators_json_shape_antm():
    doc = build_indicators(fixture_snapshot("ANTM"))

    assert doc["symbol"] == "ANTM"
    assert doc["as_of"] == "2026-09-22"
    assert doc["trigger"] == "risk"
    assert [p["id"] for p in doc["pillars"]] == [
        "ukuran_likuiditas",
        "kesehatan_keuangan",
        "valuasi",
        "kepemilikan",
        "perilaku_harga",
        "peristiwa",
    ]
    assert set(doc["summary_counts"]) == {
        "kuat",
        "wajar",
        "perhatian",
        "bermasalah",
        "tidak_tersedia",
        "tidak_berlaku",
    }
    assert doc["dismissed"] == []
    first = doc["pillars"][0]["indicators"][0]
    assert first["id"] == "free_float"
    assert first["is_new"] is None and first["since"] is None
    assert doc["score"]["grade"] == "A"


def test_unavailable_lists_tidak_tersedia_ids():
    snap = with_overview(fixture_snapshot("ANTM"), free_float=None)

    assert "free_float" in build_indicators(snap)["unavailable"]


def test_dumps_is_deterministic():
    snap = fixture_snapshot("ANTM")

    first = dumps(build_indicators(snap))
    assert dumps(build_indicators(snap)) == first
    assert json.loads(first)["symbol"] == "ANTM"


AS_OF = date(2026, 9, 22)


def with_market(
    snap: TickerSnapshot,
    close: float,
    volume: int,
    days: int = 60,
    board: str = "Main",
    dividends: list | None = None,
    splits: list | None = None,
    extra_bars: list | None = None,
) -> TickerSnapshot:
    bars = (extra_bars or []) + [
        Bar(
            date=date.fromordinal(AS_OF.toordinal() - i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=volume,
        )
        for i in reversed(range(days))
    ]
    actions = {
        **snap.events.corporate_actions,
        "dividend": dividends or [],
        "upcoming_dividend": [],
    }
    return snap.model_copy(
        update={
            "listing_board": board,
            "price": Price(bars=bars, splits=splits or []),
            "events": snap.events.model_copy(update={"corporate_actions": actions}),
        }
    )


@pytest.mark.parametrize(
    ("close", "volume", "liquidity", "price"),
    [
        (40, 5_000, "bermasalah", "bermasalah"),
        (40, 1_000_000, "wajar", "perhatian"),
        (1_000, 1_000, "bermasalah", "wajar"),
        (1_000, 6_000, "perhatian", "wajar"),
        (40, 100_000, "perhatian", "perhatian"),
    ],
)
def test_liquidity_and_sub_51_bands(close, volume, liquidity, price):
    snap = with_market(fixture_snapshot("ANTM"), close, volume)

    assert daily_liquidity(snap).status == liquidity
    assert sub_51_price(snap).status == price


def test_sub_51_not_applicable_on_acceleration_board():
    snap = with_market(fixture_snapshot("ANTM"), 40, 5_000, board="Acceleration")

    assert sub_51_price(snap).status == "tidak_berlaku"
    assert daily_liquidity(snap).status == "bermasalah"


def test_cash_dividend_within_12_months_exempts_both():
    snap = with_market(
        fixture_snapshot("ANTM"), 40, 5_000, dividends=[{"ex_date": "2025-10-01"}]
    )

    for ind in (daily_liquidity(snap), sub_51_price(snap)):
        assert ind.status == "tidak_berlaku"
        assert "III.3" in ind.note
        assert ind.value is not None


def test_dividend_older_than_12_months_does_not_exempt():
    snap = with_market(
        fixture_snapshot("ANTM"), 40, 5_000, dividends=[{"ex_date": "2025-09-01"}]
    )

    assert daily_liquidity(snap).status == "bermasalah"


def test_real_antm_and_bbca_are_exempt_by_dividend():
    for symbol in ("ANTM", "BBCA"):
        snap = fixture_snapshot(symbol)
        assert daily_liquidity(snap).status == "tidak_berlaku"
        assert sub_51_price(snap).status == "tidak_berlaku"
    assert "63 hari bursa" in daily_liquidity(fixture_snapshot("ANTM")).display


def test_split_in_window_uses_bars_after_split_only():
    pre = [
        Bar(
            date=date(2026, 6, 25),
            open=500,
            high=500,
            low=500,
            close=500,
            volume=1_000_000,
        )
    ]
    snap = with_market(
        fixture_snapshot("ANTM"),
        40,
        1_000_000,
        days=30,
        extra_bars=pre,
        splits=[{"date": "2026-08-01", "split_ratio": 10}],
    )

    assert sub_51_price(snap).status == "perhatian"


def test_split_without_date_is_tidak_tersedia():
    snap = with_market(
        fixture_snapshot("ANTM"), 40, 5_000, splits=[{"split_ratio": 10}]
    )

    assert sub_51_price(snap).status == "tidak_tersedia"
    assert daily_liquidity(snap).status == "tidak_tersedia"


def test_no_bars_is_tidak_tersedia():
    snap = with_market(fixture_snapshot("ANTM"), 40, 5_000, days=0)

    assert daily_liquidity(snap).status == "tidak_tersedia"
    assert sub_51_price(snap).status == "tidak_tersedia"


def with_financials(snap: TickerSnapshot, **fields) -> TickerSnapshot:
    return snap.model_copy(
        update={"financials": snap.financials.model_copy(update=fields)}
    )


def test_pillar_2_variant_follows_sector():
    antm, bbca = fixture_snapshot("ANTM"), fixture_snapshot("BBCA")

    assert negative_equity(antm).status == "wajar"
    assert no_revenue(antm).status == "wajar"
    assert car(antm) is None and ldr_rim(antm) is None
    assert negative_equity(bbca) is None and no_revenue(bbca) is None


def test_real_bbca_car_kuat_and_ldr_wajar_with_note():
    bbca = fixture_snapshot("BBCA")

    assert car(bbca).status == "kuat"
    assert car(bbca).display == "30,37% (2025)"
    ldr = ldr_rim(bbca)
    assert ldr.status == "wajar"
    assert "84%" in ldr.note


def test_negative_equity_uses_latest_quarter_then_annual():
    antm = fixture_snapshot("ANTM")
    quarters = [
        {"date": "2026-03-31", "total_equity": 5, "revenue": 1},
        {"date": "2026-06-30", "total_equity": -1, "revenue": 2},
    ]

    assert negative_equity(with_financials(antm, quarterly=quarters)).status == (
        "bermasalah"
    )
    annual_only = with_financials(
        antm, quarterly=[], annual=[{"year": 2025, "total_equity": -3}]
    )
    assert negative_equity(annual_only).status == "bermasalah"
    missing = with_financials(
        antm, quarterly=[], annual=[{"year": 2025, "total_equity": None}]
    )
    assert negative_equity(missing).status == "tidak_tersedia"


@pytest.mark.parametrize(
    ("revenues", "status"),
    [
        ([100, 0], "bermasalah"),
        ([100, 100], "bermasalah"),
        ([100, 120], "wajar"),
        ([None, 120], "wajar"),
        ([None, None], "tidak_tersedia"),
    ],
)
def test_no_revenue(revenues, status):
    quarters = [
        {"date": f"2026-0{3 * (i + 1)}-30", "total_equity": 1, "revenue": r}
        for i, r in enumerate(revenues)
    ]
    snap = with_financials(fixture_snapshot("ANTM"), quarterly=quarters, annual=[])

    assert no_revenue(snap).status == status


@pytest.mark.parametrize(
    ("ratio", "status"),
    [
        (0.07, "bermasalah"),
        (0.08, "perhatian"),
        (0.14, "perhatian"),
        (0.1401, "kuat"),
        (None, "tidak_tersedia"),
    ],
)
def test_car_bands(ratio, status):
    snap = with_financials(
        fixture_snapshot("BBCA"),
        annual_ratios=[{"year": 2025, "capital_adequacy_ratio": ratio}],
    )

    assert car(snap).status == status


@pytest.mark.parametrize(
    ("ratio", "status", "low_note"),
    [(0.95, "bermasalah", False), (0.90, "wajar", False), (0.80, "wajar", True)],
)
def test_ldr_one_sided(ratio, status, low_note):
    snap = with_financials(
        fixture_snapshot("BBCA"),
        annual_ratios=[{"year": 2025, "loan_to_deposit_ratio": ratio}],
    )
    ind = ldr_rim(snap)

    assert ind.status == status
    assert ("84%" in ind.note) is low_note


def test_free_float_note_only_when_below_target():
    assert free_float(fixture_snapshot("ANTM")).note is None
    snap = with_overview(fixture_snapshot("ANTM"), "Main", free_float=0.13)
    assert "31 Maret 2028" in free_float(snap).note


def with_suspensions(symbol: str, as_of: date) -> TickerSnapshot:
    rows = json.loads((FIXTURES_DIR / "suspensions.json").read_text())["results"]
    snap = fixture_snapshot("ANTM")
    return snap.model_copy(
        update={
            "as_of": as_of,
            "events": snap.events.model_copy(
                update={"suspensions": normalize_suspensions(symbol, rows, as_of)}
            ),
        }
    )


def test_suspension_effective_after_as_of_counts():
    ind = suspension_uma(with_suspensions("NASI", date(2026, 9, 21)))

    assert ind.status == "bermasalah"
    assert ind.value == 1
    assert "22 September 2026" in ind.display
    assert "UMA" in ind.note


def test_no_suspension_is_wajar():
    assert suspension_uma(fixture_snapshot("ANTM")).status == "wajar"


def with_idx(snap: TickerSnapshot, notations: list[str] | None) -> TickerSnapshot:
    lists = (
        None
        if notations is None
        else IdxLists(notations=notations, as_of=AS_OF, source_url="https://idx.id/x")
    )
    return snap.model_copy(update={"idx_lists": lists})


@pytest.mark.parametrize(
    ("notations", "notation_status", "board_status"),
    [
        (["E", "X"], "bermasalah", "bermasalah"),
        (["X"], "wajar", "bermasalah"),
        (["N"], "wajar", "wajar"),
        (["Q"], "bermasalah", "wajar"),
        ([], "wajar", "wajar"),
        (None, "tidak_tersedia", "tidak_tersedia"),
    ],
)
def test_notation_indicators(notations, notation_status, board_status):
    snap = with_idx(fixture_snapshot("ANTM"), notations)

    assert special_notation(snap).status == notation_status
    assert special_monitoring_board(snap).status == board_status


def test_notation_display_explains_letters():
    ind = special_notation(with_idx(fixture_snapshot("ANTM"), ["E", "L", "X"]))

    assert ind.value == "E,L"
    assert "ekuitas negatif" in ind.display


def test_snapshot_carries_real_idx_lists():
    snap = fixture_snapshot("ANTM")

    assert snap.idx_lists.notations == []
    assert snap.idx_lists.as_of == date(2026, 9, 22)


FROZEN_IDX_CSV = Path(__file__).parent / "fixtures" / "idx" / "notasi_khusus.csv"
GOLDEN_DIR = Path(__file__).parent / "golden"


def golden_snapshot(symbol: str) -> TickerSnapshot:
    # CSV dibekukan supaya golden tidak berubah saat bot/data/idx diperbarui.
    return fixture_snapshot(symbol).model_copy(
        update={"idx_lists": idx_lists_for(symbol, FROZEN_IDX_CSV)}
    )


@pytest.mark.parametrize("symbol", ["ANTM", "BBCA"])
def test_indicators_match_golden(symbol):
    expected = (GOLDEN_DIR / f"indicators_{symbol}.json").read_text()

    assert dumps(build_indicators(golden_snapshot(symbol))) == expected


def test_indicators_ignore_raw_input_order():
    raw = raw_for("ANTM")
    shuffled = copy.deepcopy(raw)
    for key in ("daily", "quarterly", "composition", "news"):
        shuffled[key].reverse()
    shuffled["corporate_actions"]["corporate_actions"]["dividend"].reverse()

    first = dumps(build_indicators(normalize(raw, [])))
    assert dumps(build_indicators(normalize(shuffled, []))) == first
