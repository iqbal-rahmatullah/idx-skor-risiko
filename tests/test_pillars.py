import asyncio
from datetime import date, timedelta
from functools import cache

import pytest

from bot.assess import prepare
from bot.db import make_session_factory
from bot.risk.indicators.p1_ukuran import (
    broker_concentration,
    relative_liquidity,
    volume_spike,
)
from bot.risk.indicators.p2_keuangan import (
    altman_z,
    cost_to_income,
    debt_to_equity,
    nim,
    npl_proxy,
    piotroski_f,
)
from bot.risk.indicators.p3_valuasi import (
    graham_number,
    pb_vs_peer,
    pe_vs_peer,
)
from bot.risk.indicators.p4_kepemilikan import (
    insider_buying,
    insider_selling,
    retail_share_shift,
    shareholder_concentration,
)
from bot.risk.indicators.p5_harga import (
    ara_arb_frequency,
    drawdown_90d,
    unexplained_move,
    volatility_90d,
)
from bot.risk.indicators.p6_peristiwa import (
    accrual_ratio,
    dilution_event,
    negative_news,
)
from bot.sectors.client import FIXTURES_DIR, SectorsClient, fixture_transport
from bot.snapshot.models import (
    Bar,
    Broker,
    PeerStats,
    Percentiles,
    Price,
    TickerSnapshot,
)

AS_OF = date(2026, 9, 22)
TEST_SYMBOLS = ("ANTM", "BBCA", "AEGS", "BBRI", "BMRI", "BIKE", "CASH", "GOTO")


@cache
def full_snapshot(symbol: str) -> TickerSnapshot:
    async def go():
        async with SectorsClient("k", transport=fixture_transport(FIXTURES_DIR)) as c:
            with make_session_factory("sqlite://")() as session:
                return await prepare(
                    c, session, symbol, fill_peers=True, fill_broker=True
                )

    return asyncio.run(go())


def spread(center: float) -> Percentiles:
    return Percentiles(
        n=20,
        p10=center * 0.5,
        p25=center * 0.8,
        p75=center * 1.2,
        p90=center * 1.5,
        p95=center * 2,
    )


def with_peers(snap: TickerSnapshot, **metrics: Percentiles) -> TickerSnapshot:
    peers = PeerStats(
        sub_sector=snap.sub_sector,
        as_of=snap.as_of,
        members=20,
        metrics=metrics,
        years={},
    )
    return snap.model_copy(update={"peers": peers})


def series(closes: list[float], volumes: list[int] | None = None) -> list[Bar]:
    n = len(closes)
    return [
        Bar(
            date=AS_OF - timedelta(days=n - 1 - i),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=(volumes or [100_000] * n)[i],
        )
        for i, c in enumerate(closes)
    ]


def with_bars(snap: TickerSnapshot, bars: list[Bar]) -> TickerSnapshot:
    return snap.model_copy(update={"price": Price(bars=bars, splits=[])})


def test_every_indicator_runs_on_all_test_symbols():
    from bot.risk.build_json import build_indicators

    for symbol in TEST_SYMBOLS:
        doc = build_indicators(full_snapshot(symbol))
        ids = [i["id"] for p in doc["pillars"] for i in p["indicators"]]
        assert len(ids) == len(set(ids))
        assert len(ids) >= 28


def test_volume_spike_against_own_history():
    snap = full_snapshot("ANTM")
    calm = [1_000] * 60

    assert volume_spike(
        with_bars(snap, series([100.0] * 61, calm + [10_000]))
    ).status == ("bermasalah")
    assert (
        volume_spike(with_bars(snap, series([100.0] * 61, calm + [1_000]))).status
        == "wajar"
    )
    shifted = [
        b.model_copy(update={"date": b.date - timedelta(days=1)})
        for b in series([100.0] * 61)
    ]
    assert volume_spike(with_bars(snap, shifted)).status == "tidak_tersedia"


def broker_day(day: date, nets: list[int]) -> Broker:
    return Broker(
        date=day,
        top_buyers=[
            {"rank": i + 1, "broker_code": f"B{i}", "net_idr": n}
            for i, n in enumerate(nets)
        ],
        top_sellers=[],
    )


def test_broker_concentration_against_own_history():
    snap = full_snapshot("ANTM")
    history = [
        broker_day(AS_OF - timedelta(days=30 - i), [30, 30, 40]) for i in range(20)
    ]

    hot = snap.model_copy(
        update={"broker": broker_day(AS_OF, [90, 5, 5]), "broker_history": history}
    )
    usual = snap.model_copy(
        update={"broker": broker_day(AS_OF, [40, 30, 30]), "broker_history": history}
    )
    short = snap.model_copy(
        update={"broker": broker_day(AS_OF, [90, 5, 5]), "broker_history": history[:10]}
    )

    assert broker_concentration(hot).status == "bermasalah"
    assert "B0" in broker_concentration(hot).display
    assert broker_concentration(usual).status == "wajar"
    assert broker_concentration(short).status == "tidak_tersedia"
    assert "20" in broker_concentration(short).note


def test_real_antm_broker_history_has_one_empty_day():
    ind = broker_concentration(full_snapshot("ANTM"))

    assert ind.status == "tidak_tersedia"
    assert "19" in ind.note


def test_relative_liquidity_uses_subsector_p10_without_dividend_exemption():
    snap = with_bars(full_snapshot("ANTM"), series([100.0] * 60, [1_000] * 60))

    thin = with_peers(snap, avg_daily_value=spread(1_000_000))
    deep = with_peers(snap, avg_daily_value=spread(10_000))

    assert relative_liquidity(thin).status == "bermasalah"
    assert relative_liquidity(deep).status == "wajar"
    assert relative_liquidity(snap.model_copy(update={"peers": None})).status == (
        "tidak_tersedia"
    )


@pytest.mark.parametrize("symbol", ["ANTM", "BBCA"])
def test_relative_liquidity_real_is_assessed(symbol):
    assert relative_liquidity(full_snapshot(symbol)).status in ("wajar", "bermasalah")


def with_annual(snap: TickerSnapshot, annual=None, ratios=None) -> TickerSnapshot:
    update = {}
    if annual is not None:
        update["annual"] = annual
    if ratios is not None:
        update["annual_ratios"] = ratios
    return snap.model_copy(
        update={"financials": snap.financials.model_copy(update=update)}
    )


def test_debt_to_equity_against_subsector():
    snap = full_snapshot("ANTM")
    ratios = [{"year": 2025, "debt_to_equity_ratio": 3.0}]

    high = with_peers(with_annual(snap, ratios=ratios), debt_to_equity=spread(1.0))
    low = with_peers(with_annual(snap, ratios=ratios), debt_to_equity=spread(5.0))
    negative = with_peers(
        with_annual(snap, ratios=[{"year": 2025, "debt_to_equity_ratio": -2.0}]),
        debt_to_equity=spread(1.0),
    )

    assert debt_to_equity(high).status == "bermasalah"
    assert debt_to_equity(low).status == "wajar"
    assert debt_to_equity(negative).status == "tidak_berlaku"
    assert debt_to_equity(full_snapshot("BBCA")) is None


def altman_row(**overrides) -> dict:
    row = {
        "year": 2025,
        "current_assets": 400,
        "current_liabilities": 200,
        "total_assets": 1000,
        "retained_earnings": 300,
        "ebit": 150,
        "total_equity": 600,
        "total_liabilities": 400,
    }
    return row | overrides


def test_altman_zones():
    snap = full_snapshot("ANTM")

    strong = altman_z(with_annual(snap, annual=[altman_row()]))
    grey = altman_z(
        with_annual(
            snap,
            annual=[
                altman_row(
                    retained_earnings=0,
                    ebit=20,
                    total_equity=100,
                    total_liabilities=900,
                )
            ],
        )
    )
    distress = altman_z(
        with_annual(
            snap,
            annual=[
                altman_row(
                    current_assets=100,
                    retained_earnings=-300,
                    ebit=-50,
                    total_equity=-100,
                )
            ],
        )
    )

    assert strong.status == "kuat" and strong.value == pytest.approx(4.873)
    assert grey.status == "perhatian"
    assert distress.status == "bermasalah"
    assert (
        altman_z(with_annual(snap, annual=[altman_row(ebit=None)])).status
        == "tidak_tersedia"
    )
    assert altman_z(full_snapshot("BBCA")).status == "tidak_berlaku"


PIOTROSKI_FIELDS = (
    "year",
    "earnings",
    "total_assets",
    "operating_cash_flow",
    "long_term_debt",
    "current_assets",
    "current_liabilities",
    "outstanding_shares",
    "gross_profit",
    "revenue",
)
BASE_YEAR = (100, 1000, 150, 200, 300, 200, 1000, 300, 1000)


def piotroski_years(better: bool) -> list[dict]:
    latest = (
        (120, 1000, 180, 150, 360, 200, 1000, 360, 1100)
        if better
        else (-50, 1000, -10, 300, 240, 200, 1500, 240, 800)
    )
    return [
        dict(zip(PIOTROSKI_FIELDS, (year, *values), strict=True))
        for year, values in ((2023, BASE_YEAR), (2024, BASE_YEAR), (2025, latest))
    ]


def test_piotroski_extremes_and_missing_data():
    snap = full_snapshot("ANTM")

    best = piotroski_f(with_annual(snap, annual=piotroski_years(True)))
    worst = piotroski_f(with_annual(snap, annual=piotroski_years(False)))
    gap = piotroski_years(True)
    gap[1]["long_term_debt"] = None

    assert best.status == "kuat" and best.value == 9
    assert worst.status == "bermasalah" and worst.value <= 2
    missing = piotroski_f(with_annual(snap, annual=gap))
    assert missing.status == "tidak_tersedia"
    assert "long_term_debt 2024" in missing.note
    assert piotroski_f(full_snapshot("BBCA")).status == "tidak_berlaku"


def test_piotroski_real_bike_is_computed():
    ind = piotroski_f(full_snapshot("BIKE"))

    assert ind.status in ("kuat", "wajar", "bermasalah")
    assert 0 <= ind.value <= 9


def test_bank_ratios_against_other_banks():
    bank = full_snapshot("BBCA")
    ratios = [{"year": 2025, "cost_to_income_ratio": 9.0, "net_interest_margin": 0.01}]
    annual = [{"year": 2025, "allowance_for_loans": -90, "gross_loan": 1000}]
    stressed = with_peers(
        with_annual(bank, annual=annual, ratios=ratios),
        npl_proxy=spread(0.04),
        cost_to_income=spread(2.0),
        nim=spread(0.05),
    )

    assert npl_proxy(stressed).status == "bermasalah"
    assert npl_proxy(stressed).value == pytest.approx(0.09)
    assert "proksi" in npl_proxy(stressed).note
    assert cost_to_income(stressed).status == "bermasalah"
    assert nim(stressed).status == "bermasalah"
    negative = with_annual(bank, ratios=[{"year": 2025, "cost_to_income_ratio": -3.0}])
    assert cost_to_income(negative).status == "tidak_berlaku"
    assert npl_proxy(full_snapshot("ANTM")) is None


def test_real_bank_ratios_are_assessed():
    bank = full_snapshot("BBRI")

    for fn in (npl_proxy, cost_to_income, nim):
        assert fn(bank).status in ("wajar", "bermasalah", "tidak_berlaku")


def with_valuation(snap: TickerSnapshot, **row) -> TickerSnapshot:
    history = [{"year": 2026, **row}]
    return snap.model_copy(
        update={"valuation": snap.valuation.model_copy(update={"history": history})}
    )


def test_pe_and_pb_against_sector_average():
    snap = full_snapshot("ANTM")

    rich = with_valuation(snap, pe=20.0, pe_peer_avg=10.0, pb=3.0, pb_peer_avg=1.0)
    cheap = with_valuation(snap, pe=5.0, pe_peer_avg=10.0, pb=0.5, pb_peer_avg=1.0)
    loss = with_valuation(snap, pe=-4.0, pe_peer_avg=10.0, pb=-1.0, pb_peer_avg=1.0)

    assert pe_vs_peer(rich).status == "bermasalah"
    assert pb_vs_peer(rich).status == "bermasalah"
    assert pe_vs_peer(cheap).status == "wajar"
    assert pb_vs_peer(cheap).status == "wajar"
    assert pe_vs_peer(loss).status == "tidak_berlaku"
    assert pb_vs_peer(loss).status == "tidak_berlaku"
    assert pe_vs_peer(with_valuation(snap, pe=None, pe_peer_avg=10.0)).status == (
        "tidak_tersedia"
    )


def test_real_antm_valuation_matches_fixture():
    ind = pe_vs_peer(full_snapshot("ANTM"))

    assert ind.status == "wajar"
    assert "8,56" in ind.display and "9,95" in ind.display


def with_graham_inputs(snap, eps, equity, shares, price):
    financials = snap.financials.model_copy(
        update={
            "eps": eps,
            "annual": [
                {"year": 2025, "total_equity": equity, "outstanding_shares": shares}
            ],
        }
    )
    overview = snap.overview.model_copy(update={"last_close_price": price})
    return snap.model_copy(update={"financials": financials, "overview": overview})


def test_graham_number():
    snap = full_snapshot("ANTM")

    expensive = graham_number(with_graham_inputs(snap, 100.0, 1000.0, 10.0, 600.0))
    cheap = graham_number(with_graham_inputs(snap, 100.0, 1000.0, 10.0, 400.0))
    loss = graham_number(with_graham_inputs(snap, -5.0, 1000.0, 10.0, 400.0))

    assert expensive.status == "bermasalah"
    assert expensive.value == pytest.approx(474.34, abs=0.01)
    assert cheap.status == "wajar"
    assert loss.status == "tidak_berlaku"


from bot.snapshot.models import IdxLists


def with_filings(snap: TickerSnapshot, *filings: tuple[str, int]) -> TickerSnapshot:
    rows = [
        {
            "timestamp": f"{(AS_OF - timedelta(days=days)).isoformat()}T10:00:00",
            "transaction_type": kind,
            "holder_name": "Direktur A",
            "holder_type": "insider",
        }
        for kind, days in filings
    ]
    return snap.model_copy(
        update={
            "ownership": snap.ownership.model_copy(update={"insider_filings": rows})
        }
    )


def test_insider_selling_and_buying_windows():
    snap = full_snapshot("BBCA")

    recent_sell = with_filings(snap, ("sell", 10))
    old_sell = with_filings(snap, ("sell", 40))
    recent_buy = with_filings(snap, ("buy", 5))

    assert insider_selling(recent_sell).status == "bermasalah"
    assert insider_selling(old_sell).status == "wajar"
    assert insider_buying(recent_buy).status == "kuat"
    assert insider_buying(recent_buy).weight == 0
    assert insider_buying(old_sell).status == "wajar"


def test_shareholder_concentration_from_hsc_list():
    snap = full_snapshot("ANTM")
    listed = IdxLists(hsc=True, hsc_as_of=date(2026, 9, 23), hsc_source_url="https://x")

    assert shareholder_concentration(
        snap.model_copy(update={"idx_lists": listed})
    ).status == ("bermasalah")
    assert shareholder_concentration(snap).status == "wajar"
    assert shareholder_concentration(
        snap.model_copy(update={"idx_lists": None})
    ).status == ("tidak_tersedia")


def with_retail(snap: TickerSnapshot, before: int, after: int) -> TickerSnapshot:
    rows = [
        {
            "date": "2026-07-31",
            "individual_l": before,
            "individual_f": 0,
            "total_l": 100,
            "total_f": 0,
        },
        {
            "date": "2026-08-31",
            "individual_l": after,
            "individual_f": 0,
            "total_l": 100,
            "total_f": 0,
        },
    ]
    return snap.model_copy(
        update={"ownership": snap.ownership.model_copy(update={"composition": rows})}
    )


def test_retail_share_shift_needs_a_rise_above_subsector_p90():
    snap = full_snapshot("ANTM")
    calm_peers = Percentiles(n=20, p10=-0.02, p25=-0.01, p75=0.005, p90=0.01, p95=0.02)
    falling_peers = Percentiles(
        n=20, p10=-0.09, p25=-0.08, p75=-0.06, p90=-0.05, p95=-0.04
    )

    jump = with_peers(with_retail(snap, 20, 30), retail_shift=calm_peers)
    small = with_peers(with_retail(snap, 20, 20), retail_shift=calm_peers)
    drop = with_peers(with_retail(snap, 30, 28), retail_shift=falling_peers)

    assert retail_share_shift(jump).status == "bermasalah"
    assert "+10" in retail_share_shift(jump).display
    assert retail_share_shift(small).status == "wajar"
    assert retail_share_shift(drop).status == "wajar"


def test_real_retail_shift_is_assessed():
    assert retail_share_shift(full_snapshot("BBRI")).status in ("wajar", "bermasalah")


def test_volatility_and_drawdown_against_subsector():
    snap = full_snapshot("ANTM")
    wild = with_bars(snap, series([100.0, 150.0, 60.0, 140.0, 70.0] * 12))
    calm = with_bars(snap, series([100.0, 101.0] * 30))
    peers = {"volatility_90d": spread(0.1), "drawdown_90d": spread(0.1)}

    assert volatility_90d(with_peers(wild, **peers)).status == "bermasalah"
    assert drawdown_90d(with_peers(wild, **peers)).status == "bermasalah"
    assert volatility_90d(with_peers(calm, **peers)).status == "wajar"
    assert drawdown_90d(with_peers(calm, **peers)).status == "wajar"
    assert (
        volatility_90d(wild.model_copy(update={"peers": None})).status
        == "tidak_tersedia"
    )


def test_split_is_adjusted_before_drawdown():
    snap = full_snapshot("ANTM")
    bars = series([500.0] * 30 + [100.0] * 30)
    split = snap.model_copy(
        update={
            "price": Price(
                bars=bars,
                splits=[{"date": bars[30].date.isoformat(), "split_ratio": 5}],
            )
        }
    )

    assert drawdown_90d(with_peers(split, drawdown_90d=spread(0.1))).status == "wajar"


def test_ara_arb_frequency_against_subsector():
    snap = full_snapshot("ANTM")
    closes = [1000.0] * 55 + [1250.0, 1560.0, 1560.0, 1560.0, 1560.0]
    bars = series(closes)
    touched = with_peers(with_bars(snap, bars), ara_arb_touches=spread(0.5))

    ind = ara_arb_frequency(touched)
    assert ind.status == "bermasalah"
    assert ind.value == 2
    no_peers = with_bars(snap, bars).model_copy(update={"peers": None})
    assert ara_arb_frequency(no_peers).status == "tidak_tersedia"


def test_special_board_uses_ten_percent_limit():
    snap = with_bars(full_snapshot("AEGS"), series([100.0] * 59 + [110.0]))
    ind = ara_arb_frequency(with_peers(snap, ara_arb_touches=spread(0.5)))

    assert ind.value == 1


def test_price_indicators_without_split_detail_are_unavailable():
    snap = full_snapshot("ANTM")
    broken = snap.model_copy(
        update={"price": snap.price.model_copy(update={"splits": [{"split_ratio": 2}]})}
    )

    for fn in (ara_arb_frequency, volatility_90d, drawdown_90d, unexplained_move):
        ind = fn(broken)
        assert ind.status == "tidak_tersedia" and "pemecahan" in ind.note


@pytest.mark.parametrize("symbol", TEST_SYMBOLS)
def test_real_price_behaviour_is_assessed_or_explained(symbol):
    snap = full_snapshot(symbol)

    for fn in (ara_arb_frequency, volatility_90d, drawdown_90d, unexplained_move):
        ind = fn(snap)
        assert ind.status in ("wajar", "bermasalah") or ind.status == "tidak_tersedia"


def test_unexplained_move_uses_own_return_history():
    snap = full_snapshot("ANTM")
    steady = [100.0 + (i % 2) for i in range(60)]

    jump = with_bars(snap, series(steady + [120.0]))
    fall = with_bars(snap, series(steady + [80.0]))

    assert unexplained_move(jump).status == "bermasalah"
    assert "+" in unexplained_move(jump).display
    assert unexplained_move(fall).status == "wajar"
    shifted = [
        b.model_copy(update={"date": b.date - timedelta(days=1)})
        for b in series(steady)
    ]
    assert unexplained_move(with_bars(snap, shifted)).status == "tidak_tersedia"


def with_news(snap: TickerSnapshot, *items: tuple[int, list[str]]) -> TickerSnapshot:
    rows = [
        {
            "title": f"Berita {i}",
            "timestamp": f"{(AS_OF - timedelta(days=days)).isoformat()}T08:00:00",
            "tags": tags,
            "symbols": [snap.symbol],
        }
        for i, (days, tags) in enumerate(items)
    ]
    return snap.model_copy(
        update={"events": snap.events.model_copy(update={"news": rows})}
    )


def test_negative_news_needs_three_in_seven_days():
    snap = full_snapshot("ANTM")

    three = with_news(snap, (1, ["Bearish"]), (3, ["Violation"]), (6, ["Bearish"]))
    two = with_news(snap, (1, ["Bearish"]), (3, ["Bullish"]), (6, ["Bearish"]))
    stale = with_news(snap, (1, ["Bearish"]), (3, ["Bearish"]), (9, ["Bearish"]))
    after_close = with_news(snap, (-1, ["Bearish"]), (0, ["Bearish"]), (2, ["Bearish"]))

    assert negative_news(three).status == "bermasalah"
    assert negative_news(three).value == 3
    assert negative_news(two).status == "wajar"
    assert negative_news(stale).status == "wajar"
    assert negative_news(after_close).status == "bermasalah"


def with_actions(snap: TickerSnapshot, **actions: list[dict]) -> TickerSnapshot:
    merged = {**snap.events.corporate_actions, **actions}
    return snap.model_copy(
        update={"events": snap.events.model_copy(update={"corporate_actions": merged})}
    )


def test_dilution_event_in_ninety_days():
    snap = full_snapshot("ANTM")
    recent = (AS_OF - timedelta(days=20)).isoformat()

    warrant = with_actions(snap, warrant=[{"ex_date": recent}])
    undated = with_actions(snap, warrant=[{"exercise_price": 100}])

    assert dilution_event(warrant).status == "bermasalah"
    assert dilution_event(snap).status == "wajar"
    assert dilution_event(undated).status == "wajar"
    assert "tanpa tanggal" in dilution_event(undated).note
    assert dilution_event(full_snapshot("CASH")).status == "bermasalah"


def accrual_years(earnings: float, cash_flow: float) -> list[dict]:
    return [
        {"year": 2024, "total_assets": 1000},
        {
            "year": 2025,
            "earnings": earnings,
            "operating_cash_flow": cash_flow,
            "total_assets": 1000,
        },
    ]


def test_accrual_ratio_against_subsector():
    snap = full_snapshot("ANTM")

    paper = with_peers(
        with_annual(snap, annual=accrual_years(200, 50)), accrual_ratio=spread(0.02)
    )
    cash = with_peers(
        with_annual(snap, annual=accrual_years(100, 150)), accrual_ratio=spread(0.02)
    )

    assert accrual_ratio(paper).status == "bermasalah"
    assert accrual_ratio(paper).value == pytest.approx(0.15)
    assert accrual_ratio(cash).status == "wajar"
    assert accrual_ratio(full_snapshot("BBCA")).status == "tidak_berlaku"
    gap = with_annual(snap, annual=accrual_years(200, 50)[1:])
    assert accrual_ratio(with_peers(gap, accrual_ratio=spread(0.02))).status == (
        "tidak_tersedia"
    )


def test_negative_news_context_lists_counted_articles_newest_first():
    from bot.risk.build_json import build_indicators

    doc = build_indicators(full_snapshot("ANTM"))
    items = doc["context"]["negative_news"]

    assert [i["id"] for i in items] == ["berita_1", "berita_2", "berita_3", "berita_4"]
    assert [i["date"] for i in items] == [
        "2026-09-23",
        "2026-09-22",
        "2026-09-21",
        "2026-09-18",
    ]
    assert items[0]["title"].startswith("Analyst highlights nickel stock")
    assert items[0]["source"].startswith("https://")
    assert all(len(i["excerpt"]) <= 280 for i in items)
    counted = next(
        i for p in doc["pillars"] for i in p["indicators"] if i["id"] == "negative_news"
    )
    assert counted["value"] == len(items)
    assert build_indicators(full_snapshot("CASH"))["context"]["negative_news"] == []


def test_volume_spike_is_split_adjusted():
    snap = full_snapshot("ANTM")
    closes = [500.0] * 40 + [100.0] * 21
    volumes = [1_000] * 40 + [5_000] * 21
    bars = series(closes, volumes)
    split = snap.model_copy(
        update={
            "price": Price(
                bars=bars,
                splits=[{"date": bars[40].date.isoformat(), "split_ratio": 5}],
            )
        }
    )

    assert volume_spike(split).status == "wajar"
    unknown = split.model_copy(
        update={
            "price": split.price.model_copy(update={"splits": [{"split_ratio": 5}]})
        }
    )
    assert volume_spike(unknown).status == "tidak_tersedia"


def test_negative_peer_average_is_not_a_valuation_verdict():
    snap = full_snapshot("ANTM")
    peer_loss = with_valuation(
        snap, pe=12.0, pe_peer_avg=-5.3, pb=1.2, pb_peer_avg=-0.4
    )

    assert pe_vs_peer(peer_loss).status == "tidak_berlaku"
    assert pb_vs_peer(peer_loss).status == "tidak_berlaku"
