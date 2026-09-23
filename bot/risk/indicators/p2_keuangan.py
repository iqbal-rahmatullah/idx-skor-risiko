from datetime import date
from typing import Any

from bot.risk import thresholds as t
from bot.risk.format import day, idr, pct
from bot.risk.models import Indicator, make_indicator
from bot.snapshot.models import TickerSnapshot

PILLAR = "kesehatan_keuangan"


def is_financial(snap: TickerSnapshot) -> bool:
    return snap.sector == t.FINANCIAL_SECTOR


def latest(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    return next((r for r in reversed(rows) if r.get(field) is not None), None)


def period(row: dict[str, Any]) -> str:
    return str(row.get("date") or row["year"])


def period_label(row: dict[str, Any]) -> str:
    return day(date.fromisoformat(row["date"])) if row.get("date") else str(row["year"])


def negative_equity(snap: TickerSnapshot) -> Indicator | None:
    if is_financial(snap):
        return None
    fin = snap.financials
    row, source = latest(fin.quarterly, "total_equity"), "quarterly"
    if row is None:
        row, source = latest(fin.annual, "total_equity"), "annual"
    if row is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
        path = "financials.quarterly"
    else:
        value = row["total_equity"]
        status = "bermasalah" if value < 0 else "wajar"
        display = f"{idr(value)} ({period_label(row)})"
        path = f"financials.{source}[{period(row)}].total_equity"
    return make_indicator(
        t.I_X_EQUITY,
        id="negative_equity",
        pillar=PILLAR,
        label="Ekuitas negatif",
        status=status,
        value=value,
        display=display,
        threshold="ekuitas < 0: bermasalah",
        weight=3,
        evidence_path=path,
    )


def no_revenue(snap: TickerSnapshot) -> Indicator | None:
    if is_financial(snap):
        return None
    fin = snap.financials
    source = "quarterly" if latest(fin.quarterly, "revenue") else "annual"
    rows = [r for r in getattr(fin, source) if r.get("revenue") is not None]
    if not rows:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
        path = "financials.quarterly"
    else:
        last = rows[-1]
        value = last["revenue"]
        unchanged = len(rows) > 1 and rows[-2]["revenue"] == value
        status = "bermasalah" if value == 0 or unchanged else "wajar"
        display = f"{idr(value)} ({period_label(last)})"
        if unchanged:
            display += f", sama dengan {period_label(rows[-2])}"
        path = f"financials.{source}[{period(last)}].revenue"
    return make_indicator(
        t.I_X_REVENUE,
        id="no_revenue",
        pillar=PILLAR,
        label="Tanpa pendapatan usaha",
        status=status,
        value=value,
        display=display,
        threshold="pendapatan nol atau tidak berubah dari laporan sebelumnya: bermasalah",
        weight=3,
        evidence_path=path,
    )


def car(snap: TickerSnapshot) -> Indicator | None:
    if not is_financial(snap):
        return None
    row = latest(snap.financials.annual_ratios, "capital_adequacy_ratio")
    if row is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
        path = "financials.annual_ratios"
    else:
        value = row["capital_adequacy_ratio"]
        if value < t.CAR_MIN:
            status = "bermasalah"
        elif value <= t.CAR_MAX_REQUIREMENT:
            status = "perhatian"
        else:
            status = "kuat"
        display = f"{pct(value)} ({period_label(row)})"
        path = f"financials.annual_ratios[{period(row)}].capital_adequacy_ratio"
    return make_indicator(
        t.POJK_KPMM,
        id="car",
        pillar=PILLAR,
        label="Rasio kecukupan modal (CAR)",
        status=status,
        value=value,
        display=display,
        threshold=(
            f"< {pct(t.CAR_MIN)} bermasalah · {pct(t.CAR_MIN)}–{pct(t.CAR_MAX_REQUIREMENT)}"
            f" perhatian · > {pct(t.CAR_MAX_REQUIREMENT)} kuat"
        ),
        weight=3,
        evidence_path=path,
        note="buffer konservasi 2,5% untuk KBMI 3–4 belum diperhitungkan",
    )


def ldr_rim(snap: TickerSnapshot) -> Indicator | None:
    if not is_financial(snap):
        return None
    row = latest(snap.financials.annual_ratios, "loan_to_deposit_ratio")
    note = "LDR dipakai sebagai proksi RIM; RIM juga memperhitungkan surat berharga"
    if row is None:
        status, value, display = "tidak_tersedia", None, "tidak tersedia"
        path = "financials.annual_ratios"
    else:
        value = row["loan_to_deposit_ratio"]
        status = "bermasalah" if value > t.RIM_UPPER else "wajar"
        display = f"{pct(value)} ({period_label(row)})"
        path = f"financials.annual_ratios[{period(row)}].loan_to_deposit_ratio"
        if value < t.RIM_LOWER:
            note += (
                f". Di bawah batas bawah RIM {pct(t.RIM_LOWER)}: likuiditas longgar,"
                " bukan risiko bagi investor"
            )
    return make_indicator(
        t.PADG_RIM,
        id="ldr_rim",
        pillar=PILLAR,
        label="Rasio kredit terhadap dana (proksi RIM)",
        status=status,
        value=value,
        display=display,
        threshold=f"> {pct(t.RIM_UPPER)} bermasalah",
        weight=2,
        evidence_path=path,
        note=note,
    )
