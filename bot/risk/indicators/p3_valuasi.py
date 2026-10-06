from math import sqrt
from typing import Any

from bot.risk import thresholds as t
from bot.risk.format import num
from bot.risk.indicators.common import not_applicable, unavailable
from bot.risk.models import Indicator, make_indicator
from bot.risk.thresholds import Rule
from bot.snapshot.models import TickerSnapshot

PILLAR = "valuasi"


def latest_pair(
    rows: list[dict[str, Any]], field: str, peer_field: str
) -> dict[str, Any] | None:
    return next(
        (
            r
            for r in reversed(rows)
            if r.get(field) is not None and r.get(peer_field) is not None
        ),
        None,
    )


def versus_peer(
    snap: TickerSnapshot, rule: Rule, field: str, name: str, **fields: object
) -> Indicator:
    peer_field = f"{field}_peer_avg"
    fields |= {
        "pillar": PILLAR,
        "threshold": f"{name} > rata-rata perusahaan sejenis",
        "weight": 1,
    }
    row = latest_pair(snap.valuation.history, field, peer_field)
    if row is None:
        return unavailable(rule, evidence_path="valuation.history", **fields)
    value, peer = row[field], row[peer_field]
    path = f"valuation.history[{row['year']}].{field}"
    display = f"{name} {num(value)}× vs rata-rata sejenis {num(peer)}× ({row['year']})"
    if value <= 0 or peer <= 0:
        whose = f"{name}" if value <= 0 else f"Rata-rata {name} sejenis"
        return not_applicable(
            rule,
            f"{whose} tidak bermakna saat laba atau ekuitas negatif",
            value=value,
            display=display,
            evidence_path=path,
            **fields,
        )
    return make_indicator(
        rule,
        status="bermasalah" if value > peer else "wajar",
        value=value,
        display=display,
        evidence_path=path,
        **fields,
    )


def pe_vs_peer(snap: TickerSnapshot) -> Indicator:
    return versus_peer(
        snap, t.PE_PEER, "pe", "PER", id="pe_vs_peer", label="PER dibanding sejenis"
    )


def pb_vs_peer(snap: TickerSnapshot) -> Indicator:
    return versus_peer(
        snap, t.PB_PEER, "pb", "PBV", id="pb_vs_peer", label="PBV dibanding sejenis"
    )


def graham_number(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "graham_number",
        "pillar": PILLAR,
        "label": "Graham Number",
        "threshold": "harga > √(22,5 × EPS × nilai buku per saham)",
        "weight": 2,
        "evidence_path": "financials.eps",
    }
    eps = snap.financials.eps
    price = snap.overview.last_close_price
    book = next(
        (
            r
            for r in reversed(snap.financials.annual)
            if r.get("total_equity") is not None and r.get("outstanding_shares")
        ),
        None,
    )
    if eps is None or price is None or book is None:
        return unavailable(t.GRAHAM, **fields)
    bvps = book["total_equity"] / book["outstanding_shares"]
    if eps <= 0 or bvps <= 0:
        return not_applicable(
            t.GRAHAM, "butuh laba dan nilai buku per saham yang positif", **fields
        )
    value = sqrt(t.GRAHAM_FACTOR * eps * bvps)
    return make_indicator(
        t.GRAHAM,
        status="bermasalah" if price > value else "wajar",
        value=value,
        display=f"harga Rp{num(price, 0)} vs Graham Number Rp{num(value)}",
        **fields,
    )
