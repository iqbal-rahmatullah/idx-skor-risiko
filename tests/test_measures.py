from datetime import date, timedelta

import pytest

from bot.risk.measures import (
    adjust_for_splits,
    avg_daily_value,
    daily_returns,
    limit_touches,
    max_drawdown,
    percentiles,
    retail_shift,
    rsd,
    tick,
    trading_limits,
)
from bot.snapshot.models import Bar


def bars(closes, highs=None, lows=None, volumes=None, start=date(2026, 9, 1)):
    return [
        Bar(
            date=start + timedelta(days=i),
            open=c,
            high=(highs or closes)[i],
            low=(lows or closes)[i],
            close=c,
            volume=(volumes or [100] * len(closes))[i],
        )
        for i, c in enumerate(closes)
    ]


def test_percentiles_inclusive_and_min_sample():
    p = percentiles([5, 1, None, 3, 2, 4])

    assert p.n == 5
    assert p.p25 == 2.0 and p.p75 == 4.0
    assert p.p95 == pytest.approx(4.8)
    assert percentiles([1, 2, 3, None]) is None


def test_avg_daily_value_uses_close_times_volume():
    assert avg_daily_value(bars([100, 200], volumes=[10, 20])) == 2500
    assert avg_daily_value([]) is None


def test_rsd_and_drawdown():
    closes = [100.0, 120.0, 90.0, 110.0]

    assert rsd(closes) == pytest.approx(12.909944 / 105, rel=1e-5)
    assert max_drawdown(closes) == pytest.approx(0.25)
    assert max_drawdown([100.0]) is None
    assert rsd([100.0]) is None


def test_split_adjustment_divides_prices_before_split():
    series = bars([500, 500, 100, 100])

    adjusted = adjust_for_splits(series, [{"date": "2026-09-03", "split_ratio": 5}])

    assert [b.close for b in adjusted] == [100, 100, 100, 100]
    assert adjust_for_splits(series, [{"date": "2026-09-03"}]) is None
    assert adjust_for_splits(series, []) == series


def test_daily_returns():
    assert daily_returns([100.0, 110.0, 99.0]) == pytest.approx([0.1, -0.1])


@pytest.mark.parametrize(
    ("price", "expected"),
    [(150, 1), (200, 2), (499, 2), (500, 5), (2500, 10), (5000, 25)],
)
def test_tick_sizes(price, expected):
    assert tick(price) == expected


@pytest.mark.parametrize(
    ("price", "special", "up", "down"),
    [
        (100, False, 0.35, 0.15),
        (1000, False, 0.25, 0.15),
        (6000, False, 0.20, 0.15),
        (1000, True, 0.10, 0.10),
    ],
)
def test_trading_limits(price, special, up, down):
    assert trading_limits(price, special) == (up, down)


def test_limit_touches_counts_ara_and_arb_within_last_ten_days():
    closes = [1000] * 12
    highs = [1000] * 12
    lows = [1000] * 12
    highs[5] = 1245
    lows[9] = 855
    series = bars(closes, highs, lows)

    assert limit_touches(series, special=False) == 2
    assert limit_touches(series[:5], special=False) is None


def test_retail_shift_latest_month_change():
    rows = [
        {
            "date": "2026-07-31",
            "individual_l": 20,
            "individual_f": 0,
            "total_l": 50,
            "total_f": 50,
        },
        {
            "date": "2026-08-31",
            "individual_l": 25,
            "individual_f": 5,
            "total_l": 50,
            "total_f": 50,
        },
    ]

    assert retail_shift(rows) == pytest.approx(0.10)
    assert retail_shift(rows[:1]) is None


def test_flat_prices_have_zero_drawdown_not_negative_zero():
    import math

    assert math.copysign(1, max_drawdown([100.0, 100.0])) == 1
