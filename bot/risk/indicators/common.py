from bot.risk import thresholds as t
from bot.risk.models import Indicator, make_indicator
from bot.risk.thresholds import Rule
from bot.snapshot.models import Percentiles, TickerSnapshot

UNSPLIT = "ada pemecahan saham tanpa tanggal atau rasio"


def is_financial(snap: TickerSnapshot) -> bool:
    return snap.sector == t.FINANCIAL_SECTOR


def peer_metric(snap: TickerSnapshot, name: str) -> Percentiles | None:
    return snap.peers.metrics.get(name) if snap.peers else None


def no_peers(snap: TickerSnapshot) -> str:
    if snap.peers is None:
        return "distribusi subsektor belum tersedia"
    return (
        f"anggota subsektor {snap.sub_sector} yang punya data kurang dari"
        f" {t.PERCENTILE_MIN_SAMPLE}, jadi persentilnya tidak dihitung"
    )


def unavailable(rule: Rule, note: str | None = None, **fields: object) -> Indicator:
    return make_indicator(
        rule,
        status="tidak_tersedia",
        value=None,
        display="tidak tersedia",
        note=note,
        **fields,
    )


def not_applicable(rule: Rule, note: str, **fields: object) -> Indicator:
    fields.setdefault("value", None)
    fields.setdefault("display", "tidak berlaku")
    return make_indicator(rule, status="tidak_berlaku", note=note, **fields)
