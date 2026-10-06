from dataclasses import dataclass
from datetime import date

from bot.risk import thresholds as t
from bot.risk.format import day, idr, num, pct, shares
from bot.risk.indicators.common import UNSPLIT, no_peers, peer_metric, unavailable
from bot.risk.measures import adjust_for_splits, percentiles
from bot.risk.models import Indicator, make_indicator
from bot.snapshot.models import Bar, Broker, TickerSnapshot

PILLAR = "ukuran_likuiditas"


def transition_note(value: float, small: bool, as_of: date) -> str:
    target, milestone = pct(t.FREE_FLOAT_TARGET), pct(t.FREE_FLOAT_BIG_CAP_MILESTONE)
    if small:
        return (
            f"masa transisi: {target} paling lambat {day(t.SMALL_CAP_TRANSITION_END)}"
        )
    final = f"{target} paling lambat {day(t.BIG_CAP_TRANSITION_END)}"
    if as_of > t.BIG_CAP_MILESTONE_END:
        return f"masa transisi: {final}"
    if value < t.FREE_FLOAT_BIG_CAP_MILESTONE:
        return (
            f"masa transisi: {milestone} paling lambat {day(t.BIG_CAP_MILESTONE_END)},"
            f" {final}"
        )
    return (
        f"masa transisi: {target} paling lambat {day(t.BIG_CAP_MILESTONE_END)}"
        f" bila free float per 31 Maret 2026 sudah {milestone}–{target};"
        f" {final} bila saat itu di bawah {milestone}"
    )


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
        below = value is not None and value < t.FREE_FLOAT_TARGET
        note = (
            transition_note(value, small, snap.as_of)
            if below and snap.as_of <= deadline
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


def volume_spike(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "volume_spike",
        "pillar": PILLAR,
        "label": "Lonjakan volume",
        "threshold": "volume hari ini > persentil 95 volume 90 hari saham itu",
        "weight": 1,
        "evidence_path": "price.bars",
    }
    bars = adjust_for_splits(
        [b for b in snap.price.bars if b.volume is not None], snap.price.splits
    )
    if bars is None:
        return unavailable(t.VOLUME_SPIKE, UNSPLIT, **fields)
    today = bars[-1] if bars and bars[-1].date == snap.as_of else None
    usual = percentiles([b.volume for b in bars if b.date < snap.as_of])
    if today is None or usual is None:
        return unavailable(t.VOLUME_SPIKE, **fields)
    return make_indicator(
        t.VOLUME_SPIKE,
        status="bermasalah" if today.volume > usual.p95 else "wajar",
        value=today.volume,
        display=f"{shares(today.volume)} hari ini; persentil 95 90 hari: {shares(usual.p95)}",
        **fields,
    )


def top_buyer_share(broker: Broker) -> tuple[str, float] | None:
    buyers = [b for b in broker.top_buyers if (b.get("net_idr") or 0) > 0]
    if not buyers:
        return None
    total = sum(b["net_idr"] for b in buyers)
    top = max(buyers, key=lambda b: b["net_idr"])
    return top.get("broker_code", "?"), top["net_idr"] / total


def broker_concentration(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "broker_concentration",
        "pillar": PILLAR,
        "label": "Konsentrasi broker",
        "threshold": "porsi pembeli teratas > persentil 95 riwayat saham itu",
        "weight": 1,
        "evidence_path": "broker.top_buyers",
    }
    today = top_buyer_share(snap.broker) if snap.broker.date == snap.as_of else None
    history = [s for b in snap.broker_history if (s := top_buyer_share(b))]
    if today is None:
        return unavailable(
            t.BROKER_CONCENTRATION, "tidak ada pembelian bersih hari ini", **fields
        )
    if len(history) < t.BROKER_MIN_HISTORY:
        return unavailable(
            t.BROKER_CONCENTRATION,
            f"riwayat broker baru {len(history)} hari bursa, butuh {t.BROKER_MIN_HISTORY}",
            **fields,
        )
    usual = percentiles([share for _, share in history])
    code, share = today
    return make_indicator(
        t.BROKER_CONCENTRATION,
        status="bermasalah" if share > usual.p95 else "wajar",
        value=share,
        display=(
            f"broker {code} memegang {pct(share)} pembelian bersih 10 pembeli teratas;"
            f" persentil 95 riwayat: {pct(usual.p95)}"
        ),
        **fields,
    )


def relative_liquidity(snap: TickerSnapshot) -> Indicator:
    fields = {
        "id": "relative_liquidity",
        "pillar": PILLAR,
        "label": "Likuiditas dibanding subsektor",
        "threshold": "nilai transaksi harian < persentil 10 anggota subsektor yang aktif",
        "weight": 1,
        "evidence_path": "price.bars",
    }
    liq = liquidity(snap)
    peers = peer_metric(snap, "avg_daily_value")
    if liq is None:
        return unavailable(t.RELATIVE_LIQUIDITY, **fields)
    if peers is None:
        return unavailable(t.RELATIVE_LIQUIDITY, no_peers(snap), **fields)
    return make_indicator(
        t.RELATIVE_LIQUIDITY,
        status="bermasalah" if liq.avg_value < peers.p10 else "wajar",
        value=liq.avg_value,
        display=(
            f"{idr(liq.avg_value)}/hari; persentil 10 {snap.sub_sector}: {idr(peers.p10)}/hari"
        ),
        **fields,
    )
