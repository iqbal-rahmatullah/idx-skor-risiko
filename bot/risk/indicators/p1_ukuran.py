from dataclasses import dataclass
from datetime import date

from bot.risk import thresholds as t
from bot.risk.format import day, idr, num, pct, shares
from bot.risk.models import Indicator, make_indicator
from bot.snapshot.models import Bar, TickerSnapshot

PILLAR = "ukuran_likuiditas"


def free_float(snap: TickerSnapshot) -> Indicator:
    value = snap.overview.free_float
    cap = snap.overview.market_cap
    if snap.listing_board == "Acceleration":
        rule = t.I_V
        bands = [(t.FREE_FLOAT_ACCELERATION, "bermasalah")]
        note = None
    else:
        rule = t.I_A
        small = (
            snap.listing_board in t.BOARDS_WITH_CAP_TRANSITION
            and cap is not None
            and cap < t.BIG_CAP_MIN_IDR
        )
        deadline = t.SMALL_CAP_TRANSITION_END if small else t.BIG_CAP_TRANSITION_END
        if snap.as_of > deadline:
            bands = [(t.FREE_FLOAT_TARGET, "bermasalah")]
        elif small:
            bands = [(t.FREE_FLOAT_TARGET, "perhatian")]
        else:
            bands = [
                (t.FREE_FLOAT_BIG_CAP_MILESTONE, "bermasalah"),
                (t.FREE_FLOAT_TARGET, "perhatian"),
            ]
        in_transition = snap.as_of <= deadline
        below = value is not None and value < t.FREE_FLOAT_TARGET
        note = (
            f"masa transisi: 15% paling lambat {day(deadline)}"
            if in_transition and below
            else None
        )

    if value is None:
        status, display = "tidak_tersedia", "tidak tersedia"
    else:
        status = next((s for limit, s in bands if value < limit), "wajar")
        display = pct(value)
    return make_indicator(
        rule,
        id="free_float",
        pillar=PILLAR,
        label="Free float",
        status=status,
        value=value,
        display=display,
        threshold=" · ".join(f"< {pct(limit)} {s}" for limit, s in bands),
        weight=3,
        evidence_path="overview.free_float",
        note=note,
    )


@dataclass(frozen=True)
class Liquidity:
    avg_value: float
    avg_volume: float
    avg_close: float
    days: int

    @property
    def low_value(self) -> bool:
        return self.avg_value < t.LIQUIDITY_MAX_VALUE_IDR

    @property
    def low_volume(self) -> bool:
        return self.avg_volume < t.LIQUIDITY_MAX_VOLUME


def window_bars(snap: TickerSnapshot) -> list[Bar] | None:
    bars = [b for b in snap.price.bars if b.close is not None and b.volume is not None]
    split_dates = []
    for split in snap.price.splits:
        raw = split.get("date") or split.get("ex_date")
        if not raw:
            return None
        split_dates.append(date.fromisoformat(str(raw)[:10]))
    in_window = [d for d in split_dates if bars and bars[0].date < d <= snap.as_of]
    if in_window:
        latest = max(in_window)
        bars = [b for b in bars if b.date >= latest]
    return bars


def liquidity(snap: TickerSnapshot) -> Liquidity | None:
    bars = window_bars(snap)
    if not bars:
        return None
    n = len(bars)
    return Liquidity(
        avg_value=sum(b.close * b.volume for b in bars) / n,
        avg_volume=sum(b.volume for b in bars) / n,
        avg_close=sum(b.close for b in bars) / n,
        days=n,
    )


def one_year_before(d: date) -> date:
    try:
        return d.replace(year=d.year - t.DIVIDEND_EXEMPTION_YEARS)
    except ValueError:
        return d.replace(year=d.year - t.DIVIDEND_EXEMPTION_YEARS, day=28)


def dividend_exemption(snap: TickerSnapshot) -> date | None:
    """Ex-date dividen tunai terbaru bila dalam 12 bulan (I-X III.3); ex-date menjadi proksi tanggal RUPS."""
    actions = snap.events.corporate_actions
    rows = (actions.get("dividend") or []) + (actions.get("upcoming_dividend") or [])
    dates = [
        date.fromisoformat(str(r["ex_date"])[:10]) for r in rows if r.get("ex_date")
    ]
    recent = [d for d in dates if d >= one_year_before(snap.as_of)]
    return max(recent) if recent else None


def exemption_note(ex_date: date) -> str:
    return f"dikecualikan I-X III.3: dividen tunai dengan ex-date {day(ex_date)}"


def daily_liquidity(snap: TickerSnapshot) -> Indicator:
    liq = liquidity(snap)
    note = None
    if liq is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
    else:
        value = liq.avg_value
        display = (
            f"{idr(liq.avg_value)}/hari · {shares(liq.avg_volume)}/hari"
            f" (rata-rata {liq.days} hari bursa)"
        )
        hits = liq.low_value + liq.low_volume
        status = ("wajar", "perhatian", "bermasalah")[hits]
        if ex_date := dividend_exemption(snap):
            status, note = "tidak_berlaku", exemption_note(ex_date)
    return make_indicator(
        t.I_X_LIQUIDITY,
        id="daily_liquidity",
        pillar=PILLAR,
        label="Likuiditas harian",
        status=status,
        value=value,
        display=display,
        threshold=(
            f"nilai < {idr(t.LIQUIDITY_MAX_VALUE_IDR)} dan volume"
            f" < {shares(t.LIQUIDITY_MAX_VOLUME)} per hari, 3 bulan: bermasalah;"
            " salah satu: perhatian"
        ),
        weight=3,
        evidence_path="price.bars",
        note=note,
    )


# Menumpuk dengan daily_liquidity untuk saham murah tidak likuid itu disengaja (PRD §10, pilar 1).
def sub_51_price(snap: TickerSnapshot) -> Indicator:
    liq = liquidity(snap)
    note = None
    if liq is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
    else:
        value = liq.avg_close
        display = f"rata-rata Rp{num(liq.avg_close)} ({liq.days} hari bursa)"
        if liq.avg_close >= t.PRICE_MIN_IDR:
            status = "wajar"
        elif liq.low_value and liq.low_volume:
            status = "bermasalah"
        else:
            status = "perhatian"
        if snap.listing_board == "Acceleration":
            status, note = "tidak_berlaku", "dikecualikan I-X III.2: Papan Akselerasi"
        elif ex_date := dividend_exemption(snap):
            status, note = "tidak_berlaku", exemption_note(ex_date)
    return make_indicator(
        t.I_X_PRICE,
        id="sub_51_price",
        pillar=PILLAR,
        label="Harga saham sangat rendah",
        status=status,
        value=value,
        display=display,
        threshold=(
            f"harga rata-rata 3 bulan < Rp{t.PRICE_MIN_IDR} dan likuiditas rendah:"
            f" bermasalah; < Rp{t.PRICE_MIN_IDR} saja: perhatian"
        ),
        weight=3,
        evidence_path="price.bars",
        note=note,
    )
