from datetime import date, timedelta
from typing import Any

from bot.risk import thresholds as t
from bot.risk.format import day, pct, points
from bot.risk.indicators.common import no_peers, peer_metric, unavailable
from bot.risk.measures import retail_share, retail_shift
from bot.risk.models import Indicator, make_indicator
from bot.snapshot.models import TickerSnapshot

PILLAR = "kepemilikan"


def recent_filings(snap: TickerSnapshot, kind: str) -> list[dict[str, Any]]:
    start = snap.as_of - timedelta(days=t.INSIDER_WINDOW_DAYS)
    return [
        f
        for f in snap.ownership.insider_filings
        if f.get("transaction_type") == kind
        and date.fromisoformat(f["timestamp"][:10]) >= start
    ]


def filings_display(filings: list[dict[str, Any]], verb: str, start: date) -> str:
    if not filings:
        return f"tidak ada {verb} orang dalam sejak {day(start)}"
    last = filings[-1]
    when = day(date.fromisoformat(last["timestamp"][:10]))
    return (
        f"{len(filings)} {verb} orang dalam sejak {day(start)};"
        f" terakhir {last.get('holder_name', 'orang dalam')} pada {when}"
    )


def insider_selling(snap: TickerSnapshot) -> Indicator:
    sells = recent_filings(snap, "sell")
    start = snap.as_of - timedelta(days=t.INSIDER_WINDOW_DAYS)
    return make_indicator(
        t.INSIDER,
        id="insider_selling",
        pillar=PILLAR,
        label="Penjualan orang dalam",
        status="bermasalah" if sells else "wajar",
        value=len(sells),
        display=filings_display(sells, "penjualan", start),
        threshold=f"ada penjualan dalam {t.INSIDER_WINDOW_DAYS} hari",
        weight=1,
        evidence_path="ownership.insider_filings",
        note="sinyal lemah: penjualan bisa terjadi karena kebutuhan pribadi",
    )


def insider_buying(snap: TickerSnapshot) -> Indicator:
    buys = recent_filings(snap, "buy")
    start = snap.as_of - timedelta(days=t.INSIDER_WINDOW_DAYS)
    return make_indicator(
        t.INSIDER,
        id="insider_buying",
        pillar=PILLAR,
        label="Pembelian orang dalam",
        status="kuat" if buys else "wajar",
        value=len(buys),
        display=filings_display(buys, "pembelian", start),
        threshold=f"ada pembelian dalam {t.INSIDER_WINDOW_DAYS} hari: kuat; tidak masuk skor",
        weight=0,
        evidence_path="ownership.insider_filings",
    )


def shareholder_concentration(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "shareholder_concentration",
        "pillar": PILLAR,
        "label": "Kepemilikan terkonsentrasi (HSC)",
        "threshold": "tercantum di daftar Kepemilikan Saham Terkonsentrasi Tinggi BEI",
        "weight": 3,
        "evidence_path": "idx_lists.hsc",
    }
    lists = snap.idx_lists
    if lists is None or lists.hsc is None:
        return unavailable(t.HSC, **fields)
    as_of = f" (per {day(lists.hsc_as_of)})" if lists.hsc_as_of else ""
    return make_indicator(
        t.HSC,
        status="bermasalah" if lists.hsc else "wajar",
        value=lists.hsc,
        display=("tercantum di daftar HSC BEI" if lists.hsc else "tidak tercantum")
        + as_of,
        **fields,
    )


def retail_share_shift(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "retail_share_shift",
        "pillar": PILLAR,
        "label": "Pergeseran porsi ritel",
        "threshold": "naik dan > persentil 90 perubahan anggota subsektor",
        "weight": 1,
        "evidence_path": "ownership.composition",
    }
    rows = sorted(snap.ownership.composition, key=lambda r: r["date"])
    shift = retail_shift(rows)
    if shift is None:
        return unavailable(t.RETAIL_SHIFT, **fields)
    peers = peer_metric(snap, "retail_shift")
    if peers is None:
        return unavailable(t.RETAIL_SHIFT, no_peers(snap), **fields)
    latest = rows[-1]
    return make_indicator(
        t.RETAIL_SHIFT,
        status="bermasalah" if shift > 0 and shift > peers.p90 else "wajar",
        value=shift,
        display=(
            f"porsi ritel {pct(retail_share(latest))} per {day(date.fromisoformat(latest['date']))},"
            f" {points(shift)} dari bulan sebelumnya; persentil 90 subsektor: {points(peers.p90)}"
        ),
        **fields,
    )
