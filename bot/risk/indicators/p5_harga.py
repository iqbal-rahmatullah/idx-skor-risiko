from collections.abc import Callable

from bot.risk import thresholds as t
from bot.risk.format import num, pct
from bot.risk.indicators.common import UNSPLIT, no_peers, peer_metric, unavailable
from bot.risk.measures import (
    adjust_for_splits,
    closes,
    daily_returns,
    limit_touches,
    max_drawdown,
    percentiles,
    rsd,
)
from bot.risk.models import Indicator, make_indicator
from bot.risk.thresholds import Rule
from bot.snapshot.models import Bar, TickerSnapshot

PILLAR = "perilaku_harga"


def adjusted_bars(snap: TickerSnapshot) -> list[Bar] | None:
    bars = [b for b in snap.price.bars if b.close is not None]
    return adjust_for_splits(bars, snap.price.splits)


def special_board(snap: TickerSnapshot) -> bool:
    lists = snap.idx_lists
    monitored = bool(
        lists and lists.notations and t.MONITORING_BOARD_NOTATION in lists.notations
    )
    return monitored or snap.listing_board == "Acceleration"


def versus_subsector(
    snap: TickerSnapshot,
    rule: Rule,
    metric: str,
    level: int,
    measure: Callable[[list[Bar]], float | None],
    show: Callable[[float], str],
    measured: str,
    **fields: object,
) -> Indicator:
    fields |= {
        "pillar": PILLAR,
        "threshold": f"{measured} > persentil {level} anggota subsektor",
        "weight": 1,
        "evidence_path": "price.bars",
    }
    bars = adjusted_bars(snap)
    if bars is None:
        return unavailable(rule, UNSPLIT, **fields)
    value = measure(bars)
    if value is None:
        return unavailable(rule, **fields)
    peers = peer_metric(snap, metric)
    if peers is None:
        return unavailable(rule, no_peers(snap), **fields)
    limit = getattr(peers, f"p{level}")
    return make_indicator(
        rule,
        status="bermasalah" if value > limit else "wajar",
        value=value,
        display=f"{show(value)}; persentil {level} {snap.sub_sector}: {show(limit)}",
        **fields,
    )


def ara_arb_frequency(snap: TickerSnapshot) -> Indicator:
    special = special_board(snap)
    return versus_subsector(
        snap,
        t.ARA_ARB,
        "ara_arb_touches",
        95,
        lambda bars: limit_touches(bars, special),
        lambda n: f"{num(n)} kali",
        f"sentuhan batas dalam {t.LIMIT_TOUCH_DAYS} hari bursa",
        id="ara_arb_frequency",
        label="Menyentuh batas ARA/ARB",
    )


def volatility_90d(snap: TickerSnapshot) -> Indicator:
    return versus_subsector(
        snap,
        t.VOLATILITY,
        "volatility_90d",
        90,
        lambda bars: rsd(closes(bars)),
        pct,
        "simpangan baku harga 90 hari ÷ rata-ratanya",
        id="volatility_90d",
        label="Volatilitas 90 hari",
    )


def drawdown_90d(snap: TickerSnapshot) -> Indicator:
    return versus_subsector(
        snap,
        t.DRAWDOWN,
        "drawdown_90d",
        90,
        lambda bars: max_drawdown(closes(bars)),
        pct,
        "penurunan terdalam dari puncak dalam 90 hari",
        id="drawdown_90d",
        label="Penurunan terdalam 90 hari",
    )


def unexplained_move(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "unexplained_move",
        "pillar": PILLAR,
        "label": "Lonjakan harga tanpa katalis",
        "threshold": "naik > persentil 95 return harian 90 hari saham itu",
        "weight": 2,
        "evidence_path": "price.bars",
    }
    bars = adjusted_bars(snap)
    if bars is None:
        return unavailable(t.UNEXPLAINED_MOVE, UNSPLIT, **fields)
    if len(bars) < 2 or bars[-1].date != snap.as_of or not bars[-2].close:
        return unavailable(t.UNEXPLAINED_MOVE, **fields)
    usual = percentiles(daily_returns(closes(bars[:-1])))
    if usual is None:
        return unavailable(t.UNEXPLAINED_MOVE, **fields)
    today = bars[-1].close / bars[-2].close - 1
    sign = "+" if today > 0 else ""
    return make_indicator(
        t.UNEXPLAINED_MOVE,
        status="bermasalah" if today > 0 and today > usual.p95 else "wajar",
        value=today,
        display=(
            f"{sign}{pct(today)} pada hari bursa terakhir;"
            f" persentil 95 return harian 90 hari: {pct(usual.p95)}"
        ),
        **fields,
    )
