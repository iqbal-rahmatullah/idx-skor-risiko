from datetime import date, timedelta
from textwrap import shorten
from typing import Any

from bot.risk import thresholds as t
from bot.risk.format import day, pct
from bot.risk.indicators.common import (
    is_financial,
    no_peers,
    not_applicable,
    peer_metric,
    unavailable,
)
from bot.risk.indicators.p2_keuangan import peer_year
from bot.risk.models import Indicator, make_indicator
from bot.snapshot.models import TickerSnapshot

PILLAR = "peristiwa"
EXCERPT_CHARS = 280


def suspension_uma(snap: TickerSnapshot) -> Indicator:
    start = snap.as_of - timedelta(days=t.SUSPENSION_WINDOW_DAYS)
    dates = sorted(
        d
        for s in snap.events.suspensions
        if (d := date.fromisoformat(s["suspension_date"][:10])) >= start
    )
    if dates:
        status = "bermasalah"
        display = f"{len(dates)} suspensi sejak {day(start)}, terakhir {day(dates[-1])}"
    else:
        status = "wajar"
        display = f"tidak ada suspensi sejak {day(start)}"
    return make_indicator(
        t.SUSPENSION,
        id="suspension_uma",
        pillar=PILLAR,
        label="Suspensi atau UMA",
        status=status,
        value=len(dates),
        display=display,
        threshold=f"ada suspensi dalam {t.SUSPENSION_WINDOW_DAYS} hari: bermasalah",
        weight=2,
        evidence_path="events.suspensions",
        note="UMA belum tercakup karena tidak tersedia di Sectors",
    )


def explain(letter: str) -> str:
    return f"{letter} ({t.NOTATION_MEANINGS.get(letter, 'arti belum dikenali')})"


def special_notation(snap: TickerSnapshot) -> Indicator:
    lists = snap.idx_lists
    if lists is None or lists.notations is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
    else:
        problems = [n for n in lists.notations if n not in t.NON_PROBLEM_NOTATIONS]
        status = "bermasalah" if problems else "wajar"
        value = ",".join(problems)
        display = (
            ", ".join(explain(n) for n in problems)
            if problems
            else "tidak ada notasi bermasalah"
        ) + f" (per {day(lists.as_of)})"
    return make_indicator(
        t.IDX_NOTATION,
        id="special_notation",
        pillar=PILLAR,
        label="Notasi khusus BEI",
        status=status,
        value=value,
        display=display,
        threshold="ada notasi selain X, N, dan I: bermasalah",
        weight=3,
        evidence_path="idx_lists.notations",
    )


def special_monitoring_board(snap: TickerSnapshot) -> Indicator:
    lists = snap.idx_lists
    if lists is None or lists.notations is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
    else:
        listed = t.MONITORING_BOARD_NOTATION in lists.notations
        status = "bermasalah" if listed else "wajar"
        value = listed
        display = (
            "tercatat di Papan Pemantauan Khusus" if listed else "tidak tercatat"
        ) + f" (per {day(lists.as_of)})"
    return make_indicator(
        t.I_X_BOARD,
        id="special_monitoring_board",
        pillar=PILLAR,
        label="Papan Pemantauan Khusus",
        status=status,
        value=value,
        display=display,
        threshold="notasi X: bermasalah",
        weight=3,
        evidence_path="idx_lists.notations",
    )


def negative_articles(snap: TickerSnapshot) -> list[dict[str, Any]]:
    start = snap.as_of - timedelta(days=t.NEGATIVE_NEWS_DAYS)
    hits = [
        a
        for a in snap.events.news
        if date.fromisoformat(a["timestamp"][:10]) >= start
        and t.NEGATIVE_NEWS_TAGS & set(a.get("tags") or [])
    ]
    return sorted(hits, key=lambda a: a["timestamp"], reverse=True)


def negative_news_context(snap: TickerSnapshot) -> list[dict[str, Any]]:
    return [
        {
            "id": f"berita_{n}",
            "date": a["timestamp"][:10],
            "title": a["title"],
            "tags": a.get("tags") or [],
            "source": a.get("source"),
            "excerpt": shorten(a.get("body") or "", EXCERPT_CHARS, placeholder="…"),
        }
        for n, a in enumerate(negative_articles(snap), 1)
    ]


def negative_news(snap: TickerSnapshot) -> Indicator:
    start = snap.as_of - timedelta(days=t.NEGATIVE_NEWS_DAYS)
    hits = negative_articles(snap)
    return make_indicator(
        t.NEGATIVE_NEWS,
        id="negative_news",
        pillar=PILLAR,
        label="Berita negatif",
        status="bermasalah" if len(hits) >= t.NEGATIVE_NEWS_MIN else "wajar",
        value=len(hits),
        display=f"{len(hits)} berita bertag Bearish atau Violation sejak {day(start)}",
        threshold=(
            f"≥ {t.NEGATIVE_NEWS_MIN} berita negatif dalam {t.NEGATIVE_NEWS_DAYS} hari"
        ),
        weight=1,
        evidence_path="events.news",
        note="tag berlaku untuk seluruh artikel, yang bisa membahas beberapa emiten",
    )


def dilution_event(snap: TickerSnapshot) -> Indicator:
    start = snap.as_of - timedelta(days=t.DILUTION_WINDOW_DAYS)
    actions = snap.events.corporate_actions
    rows = [
        (kind, r)
        for kind in ("right_issue", "warrant")
        for r in actions.get(kind) or []
    ]
    undated = sum(not (r.get("ex_date") or r.get("date")) for _, r in rows)
    recent = sorted(
        (d, kind)
        for kind, r in rows
        if (raw := r.get("ex_date") or r.get("date"))
        and (d := date.fromisoformat(str(raw)[:10])) >= start
    )
    names = {"right_issue": "right issue", "warrant": "waran"}
    display = (
        f"{names[recent[-1][1]]} dengan tanggal {day(recent[-1][0])}"
        if recent
        else f"tidak ada right issue atau waran sejak {day(start)}"
    )
    return make_indicator(
        t.DILUTION,
        id="dilution_event",
        pillar=PILLAR,
        label="Penerbitan saham baru",
        status="bermasalah" if recent else "wajar",
        value=len(recent),
        display=display,
        threshold=f"ada right issue atau waran dalam {t.DILUTION_WINDOW_DAYS} hari",
        weight=2,
        evidence_path="events.corporate_actions",
        note=f"{undated} baris tanpa tanggal tidak dinilai" if undated else None,
    )


def accrual_ratio(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "accrual_ratio",
        "pillar": PILLAR,
        "label": "Rasio akrual",
        "threshold": "(laba − arus kas operasi) ÷ rata-rata aset > persentil 75 subsektor",
        "weight": 1,
        "evidence_path": "financials.annual",
    }
    if is_financial(snap):
        return not_applicable(
            t.ACCRUAL, "tidak dipakai untuk emiten keuangan", **fields
        )
    by_year = {r["year"]: r for r in snap.financials.annual}
    needed = ("earnings", "operating_cash_flow", "total_assets")
    years = sorted(
        (
            y
            for y, r in by_year.items()
            if all(r.get(f) is not None for f in needed)
            and (by_year.get(y - 1) or {}).get("total_assets") is not None
        ),
        reverse=True,
    )
    wanted = peer_year(snap, "accrual_ratio")
    year = wanted if wanted in years else next(iter(years), None)
    if year is None:
        return unavailable(t.ACCRUAL, **fields)
    row = by_year[year]
    assets = (row["total_assets"] + by_year[year - 1]["total_assets"]) / 2
    if assets <= 0:
        return unavailable(t.ACCRUAL, **fields)
    value = (row["earnings"] - row["operating_cash_flow"]) / assets
    fields["evidence_path"] = f"financials.annual[{year}]"
    peers = peer_metric(snap, "accrual_ratio")
    if peers is None:
        return unavailable(t.ACCRUAL, no_peers(snap), **fields)
    return make_indicator(
        t.ACCRUAL,
        status="bermasalah" if value > peers.p75 else "wajar",
        value=value,
        display=f"{pct(value)} ({year}); persentil 75 subsektor: {pct(peers.p75)}",
        **fields,
    )
