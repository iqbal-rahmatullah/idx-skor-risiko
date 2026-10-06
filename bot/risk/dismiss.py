from datetime import date

from bot.risk import thresholds as t
from bot.risk.format import day
from bot.risk.models import Indicator
from bot.snapshot.build import event_date
from bot.snapshot.models import TickerSnapshot

DISMISSABLE = frozenset({"volume_spike", "unexplained_move"})
ACTION_NAMES = {
    "dividend": "ex-date dividen",
    "upcoming_dividend": "ex-date dividen",
    "stock_split": "pemecahan saham",
    "right_issue": "right issue",
    "warrant": "waran",
    "bonus": "saham bonus",
    "agm": "RUPS",
}


def catalyst(snap: TickerSnapshot) -> str | None:
    bars = [b for b in snap.price.bars if b.close is not None]
    if len(bars) < 2 or bars[-1].date != snap.as_of:
        return None
    start, move = bars[-2].date, bars[-1].close - bars[-2].close
    sector = snap.sector_move
    if sector and move:
        same = sector.up if move > 0 else sector.down
        if same > sector.n * t.SECTOR_MAJORITY:
            direction = "naik" if move > 0 else "turun"
            return f"{same} dari {sector.n} emiten subsektor juga {direction} pada {day(snap.as_of)}"
    for kind, rows in sorted(snap.events.corporate_actions.items()):
        for row in rows or []:
            raw = event_date(row)
            if raw and start <= (when := date.fromisoformat(raw[:10])) <= snap.as_of:
                return f"{ACTION_NAMES.get(kind, kind)} pada {day(when)}"
    for article in snap.events.news:
        when = date.fromisoformat(article["timestamp"][:10])
        if start <= when <= snap.as_of:
            return f"ada berita pada {day(when)}: {article['title']}"
    return None


def apply_dismissals(
    snap: TickerSnapshot, indicators: list[Indicator]
) -> list[Indicator]:
    if not any(i.id in DISMISSABLE and i.status == "bermasalah" for i in indicators):
        return indicators
    reason = catalyst(snap)
    if reason is None:
        return indicators
    return [
        i.model_copy(update={"dismissed_reason": reason})
        if i.id in DISMISSABLE and i.status == "bermasalah"
        else i
        for i in indicators
    ]
