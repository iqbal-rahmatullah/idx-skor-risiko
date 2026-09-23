from datetime import date, timedelta

from bot.risk import thresholds as t
from bot.risk.format import day
from bot.risk.models import Indicator, make_indicator
from bot.snapshot.models import TickerSnapshot

PILLAR = "peristiwa"


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
    if lists is None:
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
    if lists is None:
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
